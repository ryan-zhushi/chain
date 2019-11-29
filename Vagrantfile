# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  # The most common configuration options are documented and commented below.
  # For a complete reference, please see the online documentation at
  # https://docs.vagrantup.com.

  # Every Vagrant development environment requires a box. You can search for
  # boxes at https://vagrantcloud.com/search.
  config.vm.box_check_update = false
  config.vm.box = "centos/7"
  config.vm.hostname = "chain"
  config.vm.network "private_network", ip: "172.17.8.103"
  config.vm.network "forwarded_port", guest: 8000, host: 8000
  config.vm.network "forwarded_port", guest: 8002, host: 8002
  config.vm.provider "virtualbox" do |vb|
    vb.memory = "4096"
    vb.cpus = 2
    vb.name = "chain"
  end

  config.vm.synced_folder ".", "/share"
  # config.vm.synced_folder ".", "/vagrant", type: "rsync",
  #   rsync__verbose: true,
  #   rsync__exclude: ['.git*', 'node_modules*','*.log','*.box','Vagrantfile']

  config.vm.provision "shell", inline: <<-SHELL
## 设置yum的阿里云源
sudo curl -o /etc/yum.repos.d/CentOS-Base.repo http://mirrors.aliyun.com/repo/Centos-7.repo
sudo sed -i -e '/mirrors.cloud.aliyuncs.com/d' -e '/mirrors.aliyuncs.com/d' /etc/yum.repos.d/CentOS-Base.repo
sudo curl -o /etc/yum.repos.d/epel.repo http://mirrors.aliyun.com/repo/epel-7.repo
sudo yum makecache

## 安装依赖包
sudo yum install -y python36 python36-devel python36-pip \
     sshpass redis
  SHELL
end
