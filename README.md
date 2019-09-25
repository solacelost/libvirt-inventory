# libvirt-inventory.py
---
A simple, self-contained inventory script (rather than plugin, which might be preferrable) to provide Ansible connectivity to libvirt domains based on their name, including globbing support. If the instances are riding a libvirt-managed network, with DHCP, and with a routable address from the place that you're running the inventory, then this will help you dynamically list and group hosts, as well as apply variables to those hosts or groups - defined before the hosts may even exist, and even on other hosts.

### Why
---
Rather than trying to load a static IP address into your instances with virt-customize, and scale that out to simultaneous deployments, when KVM is really all you need (or want) for a part of your Ansible-driven project, this inventory source will help you get there. Because these types of configurations aren't typically large-scale production-grade deployments, but rather test environments, no real consideration has been made for large-scale production environments. Instead, this is intended to facilitate a small-scale home laboratory for provisioning starting at bare-metal layers to get you to where you can toy with maybe bigger things, inside of KVM.

### What
---
A sample ini file is provided, with lots of examples and comments. libvirt-inventory.py should be placed adjacent to libvirt.ini along with the rest of your project inventory, and libvirt.ini should contain the project-specific inventory groups and variables. You can symlink libvirt-inventory.py into place on a per-project basis, if that would be simpler to maintain in case there are updates (mine, or yours...), and also do something like multiple folders with symlinks and different libvirt.ini files.

### How
---
The required virtualenv for this to function can be built using [mkvenv](https://github.com/solacelost/misc-scripts/blob/master/mkvenv.sh) if you like, but you'll need `python3-devel` on Fedora-based distros or `python3-dev` on Debian-based distros, as well as `libvirt-devel` / `libvirt-dev` and... maybe other headers? I should maybe get a good list. Chances are you have most of this stuff already if you're doing Ansible development with libvirt. mkvenv will helpfully fail if you don't and give you a log.

When called with the virtualenv in place and functional, libvirt-inventory will ssh to the remote node (if necessary) and pull the dnsmasq leases from their default (or otherwise specified) location and map the IP addresses to the hosts, flesh out the groups, and provide all additional variables at group and host levels.

### Examples
---

#### A quick peek at the environment
```
$ ll
total 6.7M
drwxrwxr-x.  4 james james  174 Sep 25 17:26 ./
drwxrwxr-x. 24 james james 4.0K Sep 25 11:33 ../
drwxrwxr-x.  7 james james  119 Sep 25 17:24 .git/
-rw-rw-r--.  1 james james   10 Sep 25 11:32 .gitignore
-rw-rw-r--.  1 james james  181 Sep 25 17:26 libvirt.ini
-rw-rw-r--.  1 james james 2.3K Sep 25 14:40 libvirt.ini.sample
-rwxrwxr-x.  1 james james  11K Sep 25 14:42 libvirt-inventory.py*
-rw-rw-r--.  1 james james 2.6K Sep 25 17:24 README.md
-rw-rw----.  1 james james   24 Sep 25 14:29 requirements.txt
-rw-rw-r--.  1 james james 6.7M Sep 25 17:24 tags
drwxrwxr-x.  5 james james   56 Sep 25 13:21 venv/

$ cat libvirt.ini
[group_rhel]
add_hosts = rhel*

[group_el]
add_hosts = rhel*,cent*
ansible_become_password = 1qaz2wsx!QAZ@WSX

[group_ubuntu]
add_hosts = ubuntu*
ansible_become_password = password

$ sudo virsh list
 Id   Name          State
-----------------------------
 1    rhel7.6       running
 2    rhel8.0       running
 3    centos7.0     running
 4    ubuntu16.04   running
```

#### A look at native script output
```
$ ./libvirt-inventory.py --list
{
    "_meta": {
        "hostvars": {
            "rhel8.0": {
                "ansible_ssh_host": "192.168.122.9"
            },
            "rhel7.6": {
                "ansible_ssh_host": "192.168.122.4"
            },
            "centos7.0": {
                "ansible_ssh_host": "192.168.122.110"
            },
            "ubuntu16.04": {
                "ansible_ssh_host": "192.168.122.209"
            }
        }
    },
    "all": {
        "children": [
            "ungrouped",
            "libvirt_guests",
            "rhel",
            "el",
            "ubuntu"
        ]
    },
    "ungrouped": {
        "children": []
    },
    "libvirt_guests": {
        "hosts": [
            "rhel8.0",
            "rhel7.6",
            "centos7.0",
            "ubuntu16.04"
        ],
        "vars": {}
    },
    "rhel": {
        "hosts": [
            "rhel8.0",
            "rhel7.6"
        ],
        "vars": {}
    },
    "el": {
        "hosts": [
            "rhel8.0",
            "rhel7.6",
            "centos7.0"
        ],
        "vars": {
            "ansible_become_password": "1qaz2wsx!QAZ@WSX"
        }
    },
    "ubuntu": {
        "hosts": [
            "ubuntu16.04"
        ],
        "vars": {
            "ansible_become_password": "password"
        }
    }
}

$ ./libvirt-inventory.py --host rhel8.0
{
    "ansible_ssh_host": "192.168.122.9"
}
```

#### Most importantly, use of the inventory with Ansible
```
$ ansible -i ./libvirt-inventory.py rhel -m ping
rhel8.0 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/libexec/platform-python"
    },
    "changed": false,
    "ping": "pong"
}
rhel7.6 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python"
    },
    "changed": false,
    "ping": "pong"
}
```
