from setuptools import setup

setup(
    name='docker-volume-manager',
    version='0.1.0',
    description='CLI tool to manage (copy and migrate) docker bind mounts and volumes',
    url='https://github.com/MatthewScholefield/docker-volume-manager',
    author='Matthew D. Scholefield',
    author_email='matthew331199@gmail.com',
    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    keywords='docker volume manager',
    py_modules=['docker_volume_manager'],
    install_requires=[
        'pyyaml'
    ],
    entry_points={
        'console_scripts': [
            'docker-volume-manager=docker_volume_manager:main'
        ],
    }
)
