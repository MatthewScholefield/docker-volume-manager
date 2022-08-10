#!/usr/bin/env python3
import json
import os
import re
import shlex
import yaml

from argparse import ArgumentParser
from collections import namedtuple
from os.path import join, basename
from subprocess import run
from time import sleep
from typing import Union, Optional, Tuple

MountedVolume = namedtuple(
    'MountedVolume', 'service_name service_path env_file ssh_host'
)
LocalVolume = namedtuple('LocalVolume', 'local_path ssh_host')
Resource = Union[MountedVolume, LocalVolume]
DumpResult = namedtuple('DumpResult', 'command_str tar_strip_components')


def extract_host(param: str) -> Tuple[Optional[str], str]:
    if ':' in param:
        host, param = param.split(':', 1)
        return host, param
    return None, param


def extract_mounted_volumes(env_file):
    host, env_file = extract_host(env_file)
    if env_file.endswith('yml'):
        docker_compose = yaml.loads(command_over_ssh('cat "{}"'.format(env_file), host))
    else:
        docker_compose = json.loads(
            run(
                command_over_ssh('jsonnet "{}" --ext-code useSwarm=false'.format(env_file), host),
                shell=True,
                check=True,
                capture_output=True,
            ).stdout
        )
    volume_names = set(docker_compose['volumes'])
    volumes = {}
    for service_name, service in docker_compose['services'].items():
        for volume_line in service.get('volumes', []):
            if ':' in volume_line:
                volume_name, service_path = volume_line.split(':', 1)
                if volume_name not in volume_names:
                    continue
                service_path = service_path.rstrip('/')
                volumes[volume_name] = MountedVolume(
                    service_name, service_path, env_file, host
                )
    return volumes


def extract_local_volumes(folder_path):
    host, folder_path = extract_host(folder_path)
    return {
        basename(path): LocalVolume(path, host)
        for raw_path in run(
            command_over_ssh(
                shell_cmd(
                    'find {} -mindepth 1 -maxdepth 1 -type d', folder_path
                ),
                host,
            ),
            capture_output=True,
            check=True,
            shell=True,
        )
        .stdout.decode()
        .split('\n')
        for path in [raw_path.rstrip('/')]
        if path.endswith('-volume')
    }


def extract_resources(path, is_docker):
    return (
        extract_mounted_volumes(path)
        if is_docker
        else extract_local_volumes(path)
    )


def get_container_id(
    service_name: str, env_file: str, host: Optional[str]
) -> str:
    container_info_lines = (
        run(
            command_over_ssh('docker ps', host),
            check=True,
            shell=True,
            capture_output=True,
        )
        .stdout.decode()
        .strip()
        .split('\n')
    )
    for line in container_info_lines:
        container_id_match = re.match(r'^[a-f0-9]{12}(?!\S)', line)
        if not container_id_match:
            continue
        container_id = container_id_match.group(0)

        full_container_name = line.split()[-1]
        if re.search(r'(?<![a-zA-Z]){}(?![a-zA-Z]|-[a-z])'.format(re.escape(service_name)), full_container_name):
            return container_id
    raise RuntimeError('Could not find running container for {}'.format(service_name))


def shell_cmd(__command: str, *args: str, **kwargs: str) -> str:
    return __command.format(
        *map(shlex.quote, args),
        **{k: shlex.quote(v) for k, v in kwargs.items()},
    )


def command_over_ssh(command: str, host: Optional[str]) -> str:
    if not host:
        return command
    return shell_cmd('ssh -x {} {}', host, command)


def command_dump(resource: Resource) -> DumpResult:
    if isinstance(resource, LocalVolume):
        return DumpResult(
            command_over_ssh(
                shell_cmd('tar -c -C {} .', resource.local_path),
                resource.ssh_host,
            ),
            0,
        )
    elif isinstance(resource, MountedVolume):
        return DumpResult(
            command_over_ssh(
                shell_cmd(
                    'docker cp {container}:{path} -',
                    container=get_container_id(
                        resource.service_name,
                        resource.env_file,
                        resource.ssh_host,
                    ),
                    path=resource.service_path,
                ),
                resource.ssh_host,
            ),
            1,
        )
    else:
        assert False


def command_load(resource: Resource, dump_result: DumpResult):
    if isinstance(resource, LocalVolume):
        return command_over_ssh(
            shell_cmd(
                'tar xvf - --strip-components={strip_components} -C {path}',
                strip_components=str(dump_result.tar_strip_components),
                path=resource.local_path,
            ),
            resource.ssh_host,
        )
    elif isinstance(resource, MountedVolume):
        assert dump_result.tar_strip_components == 0
        return command_over_ssh(
            shell_cmd(
                'docker cp - {}:{}',
                get_container_id(
                    resource.service_name, resource.env_file, resource.ssh_host
                ),
                resource.service_path,
            ),
            resource.ssh_host,
        )
    else:
        assert False


def perform_copy(src: Resource, dest: Resource, volume_name: str):
    print()
    print(f'=== {volume_name} ===')
    dump_result = command_dump(src)
    load_command_str = command_load(dest, dump_result)
    run(
        f'{dump_result.command_str} | {load_command_str}',
        shell=True,
        check=True,
    )


def perform_delete(resource: Resource, volume_name: str):
    print(f'Deleting destination {volume_name}...')
    sleep(0.5)  # Allow time to ctrl+c
    if isinstance(resource, MountedVolume):
        run(command_over_ssh(shell_cmd(
            'docker exec {container} /bin/sh -c {command}',
            container=get_container_id(
                resource.service_name,
                resource.env_file,
                resource.ssh_host,
            ),
            command='rm -rvf {}'.format(join(resource.service_path, '*')),
        ), resource.ssh_host), shell=True, check=True)
    elif isinstance(resource, LocalVolume):
        run(command_over_ssh('rm -rvf {}'.format(join(resource.local_path, '*')), resource.ssh_host), shell=True, check=True)
    else:
        assert False


def main():
    parser = ArgumentParser(
        description=(
            'Tool to copy docker volume data between running '
            'containers and local paths, across ssh'
        )
    )
    parser.add_argument(
        'src',
        help=(
            'A docker-compose.yml/.env.*.jsonnet file for deployment '
            'to copy from or folder path to copy from. Can include ssh'
            ' host prefix like foo-machine:/home/foo/project/.env.prod.jsonnet'
        ),
    )
    parser.add_argument(
        'dest',
        help=(
            'A docker-compose.yml/.env.*.jsonnet file for deployment to'
            ' copy to or folder path to copy to. Can include ssh host '
            'prefix like foo-machine:/home/foo/project/.env.prod.jsonnet'
        ),
    )
    parser.add_argument(
        '-v',
        '--volumes',
        nargs='+',
        help='List of volumes to copy. Default: all',
    )
    parser.add_argument(
        '--delete-before-copy',
        action='store_true',
        help='Delete files in destination before copying'
    )
    args = parser.parse_args()

    if os.geteuid() == 0:
        parser.error('Must not be run as root!')

    src_is_docker = args.src.lower().endswith('jsonnet')
    dest_is_docker = args.dest.lower().endswith('jsonnet')

    if src_is_docker and dest_is_docker:
        parser.error(
            "Source and destination can't be mounted "
            'volumes due to technical constraints'
        )

    src_resources = extract_resources(args.src, src_is_docker)

    args.volumes = args.volumes or list(src_resources)
    not_found_resources = set(args.volumes) - set(src_resources)
    if not_found_resources:
        parser.error(
            f"The following resources weren't found in {args.src}: {not_found_resources}"
        )

    if src_is_docker and not dest_is_docker:
        host, path = extract_host(args.dest)
        path_args = ' '.join(
            shlex.quote(join(path, volume)) for volume in args.volumes
        )
        run(
            command_over_ssh(f'mkdir -p {path_args}', host),
            shell=True,
            check=True,
        )

    dest_resources = extract_resources(args.dest, dest_is_docker)
    for volume in args.volumes:
        if volume in dest_resources:
            if args.delete_before_copy:
                perform_delete(dest_resources[volume], volume)
            perform_copy(src_resources[volume], dest_resources[volume], volume)
        else:
            raise RuntimeError(
                f'Could not find volumes {volume} in destination {args.dest}!'
            )

    print('Copying for all volumes complete!')


if __name__ == '__main__':
    main()
