import chardet
import codecs
import csv
import json
import time
import logging
from io import StringIO
from os import system

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, HttpResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, View, CreateView, UpdateView, DetailView
from guardian.decorators import permission_required_or_404

from asset.models import AssetInfo, AssetLoginUser, AssetProject, AssetBusiness
from asset.models import AssetInfo as Asset
from chain import settings
from index.password_crypt import encrypt_p, decrypt_p
from name.models import Names
from tasks.models import Variable
from tasks.tasks import ansbile_asset_hardware
from .form import AssetForm, FileForm, AssetUserForm, AssetProjectForm, AssetBusinessForm

logger = logging.getLogger('asset')
from pure_pagination import PageNotAnInteger, Paginator

class AssetListAll(LoginRequiredMixin, ListView):
    """
    资产信息 列表
    """
    template_name = 'asset/asset.html'
    model = AssetInfo
    queryset = AssetInfo.objects.all()
    ordering = ('-id',)

    def get_context_data(self, **kwargs):
        """
        获取系统用户,再获取用户的组  根据组 去判断  资产所属的资产项目 是否 有 读取的权限
        :return:  返回有 读取权限的资产
        """
        try:
            page = self.request.GET.get('page', 1)
        except PageNotAnInteger as e:
            page = 1
        p = Paginator(self.queryset, getattr(settings,'DISPLAY_PER_PAGE'), request=self.request)

        asset_list = p.page(page)
        # 左侧导航站展开  "asset_active": "active",
        context = {
            "asset_active": "active",
            "asset_list_active": "active",
            "asset_list":asset_list,
            "web_ssh": getattr(settings, 'web_ssh'),
            "web_port": getattr(settings, 'web_port'),
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)



    def get_queryset(self):
        """
        资产信息 查询功能
        """
        name = Names.objects.get(username=self.request.user)
        self.queryset = super().get_queryset()
        excluded_assets = []
        for i in self.queryset:
            projects = AssetInfo.objects.get(hostname=i).project
            project_obj = AssetProject.objects.get(projects=projects)
            hasperm = name.has_perm('read_assetproject', project_obj)
            if not hasperm:
                excluded_assets.append(i)
        self.queryset = self.queryset.exclude(hostname__in=excluded_assets)
        if self.request.GET.get('name'):
            query = self.request.GET.get('name', None)
            self.queryset = self.queryset.filter(
                Q(network_ip=query) | Q(hostname=query) | Q(inner_ip=query) | Q(project__projects=query)).order_by(
                '-id')
        elif self.request.GET.get('project'):
            project = self.request.GET.get('project', None)
            business = self.request.GET.get('business', None)
            if business is not None:
                pro = AssetProject.objects.get(id=int(project)).projects
                self.queryset = self.queryset.filter(Q(project__projects=pro), Q(business__business=business)).order_by(
                    '-id')
            else:
                self.queryset = self.queryset.filter(Q(project__projects=project)).order_by('-id')
        return self.queryset


class AssetAdd(LoginRequiredMixin, CreateView):
    """
    资产信息 增加
    """

    model = AssetInfo
    form_class = AssetForm
    template_name = 'asset/asset-add-update.html'
    success_url = reverse_lazy('asset:asset_list')

    @method_decorator(permission_required_or_404('asset.add_assetinfo'))
    def dispatch(self, *args, **kwargs):
        # 权限验证  是否有资产 添加权限
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_list_active": "active",
        }
        if '__next__' in self.request.POST:
            context['i__next__'] = self.request.POST['__next__']
        else:
            try:
                context['i__next__'] = self.request.META['HTTP_REFERER']
            except Exception as e:
                logger.error(e)
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetUpdate(LoginRequiredMixin, UpdateView):
    """
    资产信息  更新
    """

    model = AssetInfo
    form_class = AssetForm
    template_name = 'asset/asset-add-update.html'
    success_url = reverse_lazy('asset:asset_list')

    def dispatch(self, *args, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        name = Names.objects.get(username=self.request.user)
        project = AssetInfo.objects.get(id=pk).project
        project_obj = AssetProject.objects.get(projects=project)
        hasperm = name.has_perm('change_assetproject', project_obj)
        if not hasperm:
            return HttpResponse(status=500)
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_list_active": "active",
        }
        if '__next__' in self.request.POST:
            context['i__next__'] = self.request.POST['__next__']
        else:
            try:
                context['i__next__'] = self.request.META['HTTP_REFERER']
            except Exception as e:
                logger.error(e)
        kwargs.update(context)
        return super().get_context_data(**kwargs)

    def get_success_url(self):
        self.url = self.request.POST['__next__']
        return self.url


class AssetDetail(LoginRequiredMixin, DetailView):
    """
     资产信息 详细
    """
    model = AssetInfo
    form_class = AssetForm
    template_name = 'asset/asset-detail.html'

    def dispatch(self, *args, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        name = Names.objects.get(username=self.request.user)
        project = AssetInfo.objects.get(id=pk).project
        project_obj = AssetProject.objects.get(projects=project)
        hasperm = name.has_perm('read_assetproject', project_obj)
        if not hasperm:
            return HttpResponse(status=500)
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        detail = AssetInfo.objects.get(id=pk)
        var_all = Variable.objects.filter(assets=pk).values()
        context = {
            "asset_active": "active",
            "asset_list_active": "active",
            "assets": detail,
            "nid": pk,
            "vars": var_all,
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetAllDel(LoginRequiredMixin, View):
    """
    资产单个删除 批量删除
    """
    model = AssetInfo

    @staticmethod
    def post(request):
        ret = {'status': True, 'error': None, }
        name = Names.objects.get(username=request.user)
        try:
            if request.POST.get('nid'):
                ids = request.POST.get('nid', None)
                project = AssetInfo.objects.get(id=ids).project
                project_obj = AssetProject.objects.get(projects=project)
                hasperm = name.has_perm('delete_assetproject', project_obj)
                if not hasperm:
                    ret['status'] = False
                    ret['error'] = "没有删除权限"
                    return HttpResponse(json.dumps(ret))
                else:
                    AssetInfo.objects.get(id=ids).delete()
            else:
                ids = request.POST.getlist('id', None)
                idstring = ','.join(ids)
                assets = AssetInfo.objects.extra(where=['id IN (' + idstring + ')'])
                for i in assets:
                    project = AssetInfo.objects.get(hostname=i).project
                    project_obj = AssetProject.objects.get(projects=project)
                    hasperm = name.has_perm('delete_assetproject', project_obj)
                    if not hasperm:
                        ret['status'] = False
                        ret['error'] = "没有删除权限{0}".format(i)
                    else:
                        AssetInfo.objects.get(hostname=i).delete()
        except Exception as e:
            ret['status'] = False
            ret['error'] = '删除请求错误,没有权限{}'.format(e)
        finally:
            return HttpResponse(json.dumps(ret))


class AssetHardwareUpdate(LoginRequiredMixin, View):
    """
    资产硬件    异步更新
    """
    model = AssetInfo

    @staticmethod
    def post(request):
        ret = {'status': True, 'error': None, }
        try:
            if request.POST.get('nid'):
                ids = request.POST.get('nid', None)
                asset_obj = AssetInfo.objects.get(id=ids)
                try:
                    asset_obj.user.hostname
                except Exception as e:
                    logger.error(e)
                    ret['status'] = False
                    ret['error'] = '未关联用户，请关联后再更新'.format(e)
                    return HttpResponse(json.dumps(ret))
                assets = [{"hostname": asset_obj.hostname,
                           "ip": asset_obj.network_ip,
                           "port": asset_obj.port,
                           "username": asset_obj.user.username,
                           "password": decrypt_p(asset_obj.user.password),
                           "private_key": asset_obj.user.private_key.name
                           }]
                ansbile_asset_hardware.delay(ids, assets)
        except Exception as e:
            logger.error(e)
            ret['status'] = False
            ret['error'] = '获取资产信息错误{}'.format(e)
        finally:
            return HttpResponse(json.dumps(ret))


class AssetExport(View):
    """
    资产 导出  导出全部
    """

    def get(self, request):
        # qs = asset.objects.all()
        # return render_to_csv_response(qs)

        fields = [
            field for field in Asset._meta.fields
            if field.name not in [
                'date_created'
            ]
        ]
        filename = 'assets.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="%s"' % filename
        response.write(codecs.BOM_UTF8)
        writer = csv.writer(
            response,
            dialect='excel',
            quoting=csv.QUOTE_MINIMAL)

        header = [field.verbose_name for field in fields]
        writer.writerow(header)

        name = Names.objects.get(username=request.user)
        assets = []
        for i in AssetInfo.objects.all():
            project = AssetInfo.objects.get(hostname=i).project
            project_obj = AssetProject.objects.get(projects=project)
            hasperm = name.has_perm('read_assetproject', project_obj)
            if hasperm:
                assets.append(i)

        for asset_ in assets:
            data = [getattr(asset_, field.name) for field in fields]
            writer.writerow(data)

        return response

    @staticmethod
    def post(request):
        name = Names.objects.get(username=request.user)
        ids = request.POST.getlist('id', None)
        idstring = []
        for i in ids:
            project = AssetInfo.objects.get(id=i).project
            project_obj = AssetProject.objects.get(projects=project)
            hasperm = name.has_perm('read_assetproject', project_obj)
            if hasperm:
                idstring.append(i)
        idstring2 = ','.join(idstring)
        qs = AssetInfo.objects.extra(where=['id IN (' + idstring2 + ')']).all()
        # return  render_to_csv_response(qs)
        fields = [
            field for field in Asset._meta.fields
            if field.name not in [
                'date_created'
            ]
        ]
        filename = 'assets.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="%s"' % filename
        response.write(codecs.BOM_UTF8)

        writer = csv.writer(
            response,
            dialect='excel',
            quoting=csv.QUOTE_MINIMAL)

        header = [field.verbose_name for field in fields]
        writer.writerow(header)
        for asset_ in qs:
            data = [getattr(asset_, field.name) for field in fields]
            writer.writerow(data)
        return response


def get_object_or_none(model, **kwargs):
    try:
        obj = model.objects.get(**kwargs)
    except model.DoesNotExist:
        return None
    return obj


@login_required
def AssetImport(request):
    """
    资产 导入
    :param request:
    :return:
    """
    form = FileForm()

    if request.method == "POST":
        form = FileForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data['file']
            det_result = chardet.detect(f.read())
            f.seek(0)  # reset file seek index
            file_data = f.read().decode(det_result['encoding']).strip(codecs.BOM_UTF8.decode())
            csv_file = StringIO(file_data)
            reader = csv.reader(csv_file)
            csv_data = [row for row in reader]
            fields = [
                field for field in Asset._meta.fields
                if field.name not in [
                    'date_created'
                ]
            ]
            header_ = csv_data[0]
            mapping_reverse = {field.verbose_name: field.name for field in fields}
            attr = [mapping_reverse.get(n, None) for n in header_]

            created, updated, failed = [], [], []
            assets = []
            for row in csv_data[1:]:
                if set(row) == {''}:
                    continue

                asset_dict = dict(zip(attr, row))
                id_ = asset_dict.pop('id', 0)
                for k, v in asset_dict.items():
                    v = v.strip()
                    if k == 'is_active':
                        v = True if v in ['TRUE', 1, 'true'] else False
                    elif k in ['port', ]:
                        try:
                            v = int(v)
                        except ValueError:
                            v = 22
                    elif k in ['project']:
                        try:
                            v = AssetProject.objects.get(projects=v)
                        except Exception as e:
                            v = None
                    elif k in ['business']:
                        try:
                            v = AssetBusiness.objects.get(business=v)
                        except Exception as e:
                            v = None
                    elif k in ['user', ]:
                        try:
                            v = AssetLoginUser.objects.get(user=v)
                        except Exception as e:
                            v = None
                    elif k in ['ctime', 'utime' ]:
                        v = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
                    asset_dict[k] = v

                asset = get_object_or_none(Asset, id=id_) if id_ else None
                if not asset:
                    try:
                        if len(Asset.objects.filter(hostname=asset_dict.get('hostname'))):
                            raise Exception('已经创建了，无法重复创建 此 hostname')
                        with transaction.atomic():
                            asset = Asset.objects.create(**asset_dict)
                            created.append(asset_dict['hostname'])
                            assets.append(asset)
                    except Exception as e:
                        failed.append('%s: %s' % (asset_dict['hostname'], str(e)))
                else:
                    for k, v in asset_dict.items():
                        if v:
                            setattr(asset, k, v)
                    try:
                        asset.save()
                        updated.append(asset_dict['hostname'])
                    except Exception as e:
                        failed.append('%s: %s' % (asset_dict['hostname'], str(e)))

            data = {
                'created': created,
                'created_info': 'Created {}'.format(len(created)),
                'updated': updated,
                'updated_info': 'Updated {}'.format(len(updated)),
                'failed': failed,
                'failed_info': 'Failed {}'.format(len(failed)),
                'valid': True,
                'msg': 'Created: {}. Updated: {}, Error: {}'.format(
                    len(created), len(updated), len(failed))
            }

            return render(request, 'asset/asset-import.html', {'form': form,
                                                               "asset_active": "active",
                                                               "asset_list_active": "active",
                                                               "msg": data})

    return render(request, 'asset/asset-import.html',
                  {'form': form, "asset_active": "active", "asset_list_active": "active", })


@login_required
def AssetZtree(request):
    """
    获取 区域 资产树 的相关数据
    :param request:
    :return:
    """
    business = AssetBusiness.objects.all()
    managers = AssetProject.objects.values("projects").distinct()
    name = Names.objects.get(username=request.user)
    manager = []
    for i in managers:
        project_obj = AssetProject.objects.get(projects=i['projects'])
        hasperm = name.has_perm('read_assetproject', project_obj)
        if hasperm:
            manager.append(i)

    data = [{"id": "0", "pId": "0", "name": "项目"}, ]
    for i in manager:
        project_id = AssetProject.objects.get(projects=i['projects']).id
        data.append({"id": "000{0}".format(project_id), "n": i['projects'], "pId": "0",
                     "name": "{0}({1})".format(i['projects'],
                                               AssetInfo.objects.filter(project__projects=i['projects']).count()),
                     "page": "xx.action"}, )
        for b in business:
            count = AssetInfo.objects.filter(project__projects=i['projects']).filter( business__business=b.business).count()
            if count == 0:
                continue
            data.append({"id": b.business, "pId": "000{0}".format(project_id), "name": "{0}({1})".format(b.business,count), "page": "xx.action"}, )
    return HttpResponse(json.dumps(data), content_type='application/json')


class AssetUserListAll(LoginRequiredMixin, ListView):
    """
    资产用户列表
    """
    template_name = 'asset/asset-user.html'
    model = AssetLoginUser

    def get_context_data(self, **kwargs):
        name = Names.objects.get(username=self.request.user)
        assets_user = []
        for i in AssetLoginUser.objects.all():
            project = AssetLoginUser.objects.get(hostname=i).project
            project_obj = AssetProject.objects.get(projects=project)
            hasperm = name.has_perm('read_assetproject', project_obj)
            if hasperm:
                assets_user.append(i)
        context = {
            "asset_active": "active",
            "asset_user_list": assets_user,
            "asset_user_list_active": "active",

        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetUserAdd(LoginRequiredMixin, CreateView):
    """
    资产用户 增加
    """
    model = AssetLoginUser
    form_class = AssetUserForm
    template_name = 'asset/asset-user-add-update.html'
    success_url = reverse_lazy('asset:asset_user_list')

    @method_decorator(permission_required_or_404('asset.add_assetloginuser'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_user_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        forms = form.save()
        password_form = form.cleaned_data['password']
        private_key = form.cleaned_data['private_key']
        if password_form is not None:
            password = encrypt_p(password_form)
            forms.password = password
            forms.save()
        if private_key is not None:
            try:
                name = form.cleaned_data['hostname']
                private_key_path = AssetLoginUser.objects.get(hostname=name).private_key.name
                system("chmod  600  {0}".format(private_key_path))
            except Exception as e:
                logger.error(e)
        return super().form_valid(form)


class AssetUserUpdate(LoginRequiredMixin, UpdateView):
    """
    资产用户 更新
    """
    model = AssetLoginUser
    form_class = AssetUserForm
    template_name = 'asset/asset-user-add-update.html'
    success_url = reverse_lazy('asset:asset_user_list')

    def dispatch(self, *args, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        name = Names.objects.get(username=self.request.user)
        project = AssetLoginUser.objects.get(id=pk).project
        project_obj = AssetProject.objects.get(projects=project)
        hasperm = name.has_perm('change_assetproject', project_obj)
        if not hasperm:
            return HttpResponse(status=500)
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_user_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        obj = AssetLoginUser.objects.get(id=pk)

        old_password = obj.password
        new_password = form.cleaned_data['password']
        private_key = form.cleaned_data['private_key']
        forms = form.save()
        if new_password is None:
            forms.password = old_password
        else:
            password = encrypt_p(new_password)
            forms.password = password

        forms.save()
        if private_key is not None:
            name = form.cleaned_data['hostname']
            private_key_path = AssetLoginUser.objects.get(hostname=name).private_key.name
            system("chmod  600  {0}".format(private_key_path))

        return super().form_valid(form)


class AssetUserDetail(LoginRequiredMixin, DetailView):
    """
    资产用户详细
    """
    model = AssetLoginUser
    template_name = 'asset/asset-user-detail.html'

    def dispatch(self, *args, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        name = Names.objects.get(username=self.request.user)
        pro = AssetLoginUser.objects.get(id=pk).project
        proj = AssetProject.objects.get(projects=pro)
        hasperm = name.has_perm('read_assetproject', proj)
        if not hasperm:
            return HttpResponse(status=500)
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        detail = AssetLoginUser.objects.get(id=pk)

        context = {
            "asset_active": "active",
            "asset_user_list_active": "active",
            "assets": detail,
            "nid": pk,
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


@login_required(login_url="/login.html")
def AssetUserAsset(request, pk):
    """
    资产用户 对应 资产信息
    """
    obj = AssetInfo.objects.filter(user=pk)
    return render(request, "asset/asset-user-asset.html", {"nid": pk, "assets_list": obj, "asset_active": "active",
                                                           "asset_user_list_active": "active"})


class AssetUserAllDel(LoginRequiredMixin, View):
    """
    资产用户删除
    """
    model = AssetLoginUser

    @staticmethod
    def post(request):
        ret = {'status': True, 'error': None, }
        name = Names.objects.get(username=request.user)
        try:
            if request.POST.get('nid'):
                ids = request.POST.get('nid', None)
                project = AssetLoginUser.objects.get(id=ids).project
                project_obj = AssetProject.objects.get(projects=project)
                hasperm = name.has_perm('delete_assetproject', project_obj)
                if not hasperm:
                    ret['status'] = False
                    ret['error'] = "没有删除权限"
                    return HttpResponse(json.dumps(ret))
                else:
                    AssetLoginUser.objects.get(id=ids).delete()
            else:
                ids = request.POST.getlist('id', None)
                idstring = ','.join(ids)
                assets = AssetLoginUser.objects.extra(where=['id IN (' + idstring + ')'])
                for i in assets:
                    pro = AssetLoginUser.objects.get(hostname=i).project
                    proj = AssetProject.objects.get(projects=pro)
                    rets = name.has_perm('delete_assetproject', proj)
                    if not rets:
                        ret['status'] = False
                        ret['error'] = "没有删除权限{0}".format(i)
                    else:
                        AssetLoginUser.objects.get(hostname=i).delete()
        except Exception as e:
            ret['status'] = False
            ret['error'] = '删除请求错误,没有权限{}'.format(e)
        finally:
            return HttpResponse(json.dumps(ret))


class AssetWeb(LoginRequiredMixin, View):
    """
    终端 webssh  登录
    """

    @staticmethod
    def post(request, ):
        ret = {'status': True, }
        try:
            ids = request.POST.get('id', None)
            obj = AssetInfo.objects.get(id=ids)

            name = Names.objects.get(username=request.user)
            project = AssetInfo.objects.get(id=ids).project
            project_obj = AssetProject.objects.get(projects=project)
            hasperm = name.has_perm('cmd_assetproject', project_obj)
            if not hasperm:
                ret['status'] = False
                ret['error'] = '请求错误,没有权限登录'
            else:
                ip = obj.network_ip
                port = obj.port
                username = obj.user.username
                password = obj.user.password

                try:
                    privatekey = obj.user.private_key.path
                except Exception as e:
                    logger.error(e)
                    privatekey = None

                ret.update({"ip": ip, 'port': port, "username": username,
                            'password': password, "privatekey": privatekey})

                # login_ip = request.META['REMOTE_ADDR']
        except Exception as e:
            logger.error(e)
            ret['status'] = False
            ret['error'] = '请求错误,{}'.format(e)
        finally:
            return HttpResponse(json.dumps(ret))


class AssetProjectListAll(LoginRequiredMixin, ListView):
    """
    资产项目列表
    """
    template_name = 'asset/asset-project.html'
    model = AssetProject

    def get_context_data(self, **kwargs):

        name = Names.objects.get(username=self.request.user)
        assets_project = []
        for i in AssetProject.objects.all():
            project_obj = AssetProject.objects.get(projects=i)
            hasperm = name.has_perm('read_assetproject', project_obj)
            if hasperm:
                assets_project.append(i)

        context = {
            "asset_active": "active",
            "asset_project_list_active": "active",
            "asset_project_list": assets_project
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetProjectAdd(LoginRequiredMixin, CreateView):
    """
    资产项目增加
    """
    model = AssetProject
    form_class = AssetProjectForm
    template_name = 'asset/asset-project-add-update.html'
    success_url = reverse_lazy('asset:asset_project_list')

    @method_decorator(permission_required_or_404('asset.add_assetproject'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_project_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetProjectAllDel(LoginRequiredMixin, View):
    """
    资产项目 删除
    """
    model = AssetProject

    @staticmethod
    def post(request):
        ret = {'status': True, 'error': None, }
        name = Names.objects.get(username=request.user)
        try:
            if request.POST.get('nid'):
                ids = request.POST.get('nid', None)
                project_obj = AssetProject.objects.get(id=ids).projects
                hasperm = name.has_perm('delete_assetproject', project_obj)
                if not hasperm:
                    ret['status'] = False
                    ret['error'] = "没有删除权限"
                    return HttpResponse(json.dumps(ret))
                else:
                    AssetProject.objects.get(id=ids).delete()
            else:
                ids = request.POST.getlist('id', None)
                idstring = ','.join(ids)
                assets = AssetInfo.objects.extra(where=['id IN (' + idstring + ')'])
                for i in assets:
                    pro = AssetProject.objects.get(id=ids).projects
                    rets = name.has_perm('delete_assetproject', pro)
                    if not rets:
                        ret['status'] = False
                        ret['error'] = "没有删除权限{0}".format(i)
                    else:
                        AssetProject.objects.get(hostname=i).delete()

        except Exception as e:
            ret['status'] = False
            ret['error'] = '删除请求错误,没有权限{}'.format(e)
        finally:
            return HttpResponse(json.dumps(ret))


class AssetProjectUpdate(LoginRequiredMixin, UpdateView):
    """
    资产项目更新
    """

    model = AssetProject
    form_class = AssetProjectForm
    template_name = 'asset/asset-project-add-update.html'
    success_url = reverse_lazy('asset:asset_project_list')

    def dispatch(self, *args, **kwargs):
        pk = self.kwargs.get(self.pk_url_kwarg, None)
        name = Names.objects.get(username=self.request.user)
        project_obj = AssetProject.objects.get(id=pk)
        hasperm = name.has_perm('change_assetproject', project_obj)
        if not hasperm:
            return HttpResponse(status=500)
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_project_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetBusinessListAll(LoginRequiredMixin, ListView):
    """
    资产业务 列表
    """
    template_name = 'asset/asset-business.html'
    model = AssetBusiness
    context_object_name = "business_list"
    queryset = AssetBusiness.objects.all()
    ordering = ('-id',)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_business_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetBusinessAdd(LoginRequiredMixin, CreateView):
    """
    资产业务 增加
    """
    model = AssetBusiness
    form_class = AssetBusinessForm
    template_name = 'asset/asset-business-add-update.html'
    success_url = reverse_lazy('asset:asset_business_list')

    @method_decorator(permission_required_or_404('asset.add_assetbusiness'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_business_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)


class AssetBusinessAllDel(LoginRequiredMixin, View):
    """
   资产业务 删除
    """
    model = AssetBusiness

    @method_decorator(permission_required_or_404('asset.delete_assetbusiness'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    @staticmethod
    def post(request):
        ret = {'status': True, 'error': None, }
        try:
            if request.POST.get('nid'):
                ids = request.POST.get('nid', None)
                AssetBusiness.objects.get(id=ids).delete()
            else:
                ids = request.POST.getlist('id', None)
                idstring = ','.join(ids)
                AssetBusiness.objects.extra(where=['id IN (' + idstring + ')']).delete()
        except Exception as e:
            ret['status'] = False
            ret['error'] = '删除请求错误,没有权限{}'.format(e)
        finally:
            return HttpResponse(json.dumps(ret))


class AssetBusinessUpdate(LoginRequiredMixin, UpdateView):
    """
    资产业务 更新
    """

    model = AssetBusiness
    form_class = AssetBusinessForm
    template_name = 'asset/asset-business-add-update.html'
    success_url = reverse_lazy('asset:asset_business_list')

    @method_decorator(permission_required_or_404('asset.change_assetbusiness'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            "asset_active": "active",
            "asset_business_list_active": "active",
        }
        kwargs.update(context)
        return super().get_context_data(**kwargs)
