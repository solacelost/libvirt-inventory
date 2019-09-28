#!/usr/bin/env python3
"""
libvirt-inventory.py - Libvirt dynamic inventory source for Ansible

A libvirt-managed network pool inventory for very specific use cases and
  network layouts.

Copyright (c) 2019 James Harmison

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from functools import partial
from fnmatch import fnmatch as _fnmatch
from xml.dom import minidom
import configparser
import argparse
import libvirt
import logging
import json
import sys
import os

logger = logging.getLogger('libvirt-inventory')
handler = logging.StreamHandler()
_format = '{asctime} {name} [{levelname:^9s}]: {message}'
formatter = logging.Formatter(_format, style='{')
handler.setFormatter(formatter)
logger.setLevel(logging.ERROR)
logger.addHandler(handler)


def list_vms(connection: str = None) -> list:
    """
    Returns a list of the libvirt api virDomain objects
    """
    with libvirt.open(connection) as conn:
        return conn.listAllDomains()


def decode_lease(line: str = None) -> dict:
    """
    Reads the default dnsmasq leases file format, in lieu of libvirt's json
    """
    if line is not None:
        logger.debug('Decoding non-JSON lease line: {}'.format(line))
        line = line.strip().split()
        return {
            'mac-address': line[1],
            'ip-address': line[2],
        }


def list_leases(lease_file: str = None) -> dict:
    """
    Just reads the json from file and returns it as a dict

    Connects to remote host to get file if necessary
    """
    logger.debug('Reading leases from file: {}'.format(lease_file))
    if ':' in lease_file:
        import paramiko

        host, lease_file = lease_file.split(':', 1)
        if '@' in host:
            user, host = host.split('@')
            cfg = {'hostname': host, 'username': user}
        else:
            cfg = {'hostname': host}
        logger.debug('Detected SSH requirement for leases')
        logger.debug('Determined SSH host: {}'.format(host))
        logger.debug('      File location: {}'.format(lease_file))
        client = paramiko.client.SSHClient()
        client._policy = paramiko.WarningPolicy()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.load_system_host_keys()
        ssh_config = paramiko.SSHConfig()
        user_config_file = os.path.expanduser("~/.ssh/config")
        if os.path.exists(user_config_file):
            with open(user_config_file) as f:
                ssh_config.parse(f)
        user_config = ssh_config.lookup(cfg['hostname'])
        for k in ('hostname', 'username', 'user', 'port'):
            if k in user_config:
                if k == 'user':
                    cfg['username'] = user_config[k]
                else:
                    cfg[k] = user_config[k]
        if 'proxycommand' in user_config:
            cfg['sock'] = paramiko.ProxyCommand(user_config['proxycommand'])
        logger.debug('Attempting SSH connection with:')
        logger.debug(cfg)
        client.connect(**cfg)
        _, stdout, stderr = client.exec_command('cat {}'.format(lease_file))
        stdout = str(''.join(stdout.readlines()))
        stderr = str(''.join(stderr.readlines()))
        client.close()
        logger.debug('Received stdout:')
        logger.debug(stdout)
        logger.debug('         stderr:')
        logger.debug(stderr)
        try:
            return json.loads(stdout)
        except json.decoder.JSONDecodeError:
            return [decode_lease(line) for line in stdout.split('\n')]

    with open(lease_file, 'r') as f:
        logger.debug('Lease file appears to be local, attempting to read JSON')
        try:
            return json.load(f)
        except json.decoder.JSONDecodeError:
            logger.debug('Non-JSON formatted lease found, parsing')
            f.seek(0)
            return [decode_lease(line) for line in f.readlines()]


def mac_from_vm(vm: libvirt.virDomain = None) -> str:
    """
    Parses the vm's XML to return just the mac address as a string
    """
    doc = minidom.parseString(vm.XMLDesc())
    interfaces = doc.getElementsByTagName('mac')
    return interfaces[0].getAttribute('address')


def leases_to_ip(leases: list = None, mac: str = None) -> str:
    """
    Returns the IP assigned to the mac address from the dnsmasq leases file
    """
    for lease in leases:
        logger.debug('Checking for MAC {} in {}'.format(mac, lease))
        if lease['mac-address'] == mac:
            return lease['ip-address']


def fnmatch(pattern, filename) -> bool:
    """
    Just swapping *arg order in fnmatch.fnmatch
    """
    return _fnmatch(filename, pattern)


def split_and_glob(s: str = None) -> list:
    """
    Splits the config-definition string on commas and returns a list of
    partials that will compare the comma-delimited globs from s against the
    string provided to them
    """
    ret = []
    if s is not None:
        for glob in s.split(','):
            if glob != '':
                ret.append(partial(fnmatch, glob))
    return ret


def config_dump(config: configparser.ConfigParser = None) -> dict:
    """
    Maps the config down to the method-less dict of dicts below
    """
    return {s: {v: config[s][v] for v in config[s]} for s in config.keys()}


def parse_args(args: list = None) -> dict:
    parser = argparse.ArgumentParser(description=' '.join([
        'Generate dynamic inventories for ansible using a libvirt connection',
        'and mappings of the DHCP leases granted by dnsmasq, with .ini config',
        'file support.'
    ]))
    parser.add_argument('-c', '--config', default='libvirt.ini',
                        help=('the name of a config file (adjacent to this ',
                              'script) to use'))
    parser.add_argument('-l', '--list', action='store_true',
                        help='list all identified hosts and their vars')
    parser.add_argument('-H', '--host',
                        help='output only the vars for a specific host')
    parser.add_argument('-v', '--verbose', action='count',
                        help=('make logging output more verbose (one v for '
                              'warnings, two for info, three for debug'))
    return parser.parse_args(args)


if __name__ == '__main__':
    args = parse_args(sys.argv[1:])
    if args.verbose is not None:
        logger.setLevel(40 - (min(3, args.verbose) * 10))
    logger.debug('Received args:')
    logger.debug(args)

    config = configparser.ConfigParser()
    # Case sensitivity matters
    config.optionxform = lambda option: option
    # Default options (including the default group)
    config.read_dict({
        'general': {
            'libvirt_connection': 'qemu:///system',
            'libvirt_dhcp_lease_file':
                '/var/lib/libvirt/dnsmasq/virbr0.status',
            'add_groups': '',
        },
        'group_libvirt_guests': {
            'add_hosts': '*',
        },
    })
    logger.debug('Starting config with default values:')
    logger.debug(config_dump(config))

    # Grab ini file from adjacent to script only (don't follow symlinks)
    configfile = os.path.join(
        os.path.dirname(__file__), args.config
    )
    logger.debug('Parsing configfile: {}'.format(configfile))
    config.read(configfile)
    logger.debug('Final config:')
    logger.debug(config_dump(config))

    # Basic inventory structure
    inventory = {'_meta': {'hostvars': {}},
                 'all': {'children': ['ungrouped', ]},
                 'ungrouped': {'children': []}}
    # Split out our defined group sections
    groups = {
        k.split('_', 1)[1]: dict(v) for k, v in
        config.items() if k.startswith('group_')
    }
    # Split out our defined host sections
    hosts = {
        k.split('_', 1)[1]: dict(v) for k, v in
        config.items() if k.startswith('host_')
    }
    for group in groups:
        # Initialize bare group
        logger.debug('Adding group {}'.format(group))
        inventory[group] = {
            'hosts': [],
            'vars': {},
        }
        inventory['all']['children'].append(group)
        # We'll need these glob partials later
        groups[group]['add_hosts'] = split_and_glob(
            groups[group].get('add_hosts')
        )
        # Load defined group vars
        for var in groups[group].keys():
            if not var.startswith('add_'):
                inventory[group]['vars'][var] = groups[group][var]
            elif var == 'add_children':
                children = groups[group]['add_children'].split(',')
                inventory[group]['children'] = children

    vms = list_vms(config['general']['libvirt_connection'])
    leases = list_leases(config['general']['libvirt_dhcp_lease_file'])

    logger.debug('VMs: {}'.format(vms))
    logger.debug('Leases: {}'.format(leases))

    for vm in vms:
        ip = None
        name = vm.name()
        logger.debug('Mapping libvirt domain {}'.format(name))
        if vm.isActive():
            logger.debug('VM is up')
            ip = leases_to_ip(leases, mac_from_vm(vm))
            logger.debug('VM IP: {}'.format(ip))
            if ip is not None:
                logger.debug('Adding host to _meta')
                inventory['_meta']['hostvars'][name] = {
                    'ansible_ssh_host': ip,
                }

            logger.debug('Scanning for group membership')
            for group in groups:
                for glob in groups[group]['add_hosts']:
                    if glob(name):
                        logger.debug(
                            'Adding {} to group {}'.format(name, group)
                        )
                        inventory[group]['hosts'].append(name)

    for host in hosts:
        hosts[host]['add_groups'] = split_and_glob(
            hosts[host].get('add_groups')
        )
        logger.debug('Scanning for extra group membership for {}'.format(host))
        for group in groups:
            for glob in hosts[host]['add_groups']:
                if glob(group):
                    logger.debug('Adding {} to group {}'.format(host, group))
                    inventory[group]['hosts'].append(host)
        logger.debug('Updating vars for {}'.format(host))
        for var in hosts[host].keys():
            if not var.startswith('add_'):
                logger.debug(
                    'Adding var {} value {}'.format(var, hosts[host][var])
                )
                try:
                    inventory['_meta']['hostvars'][host][var] = \
                        hosts[host][var]
                except KeyError:
                    logger.warning((
                        "Unable to add var {} to host {} "
                        "(doesn't exist?)".format(var, host)
                    ))

    if args.list:
        print(json.dumps(inventory, indent=4))
        exit(0)
    if args.host is not None:
        print(json.dumps(
            inventory['_meta']['hostvars'].get(args.host, {}), indent=4
        ))
