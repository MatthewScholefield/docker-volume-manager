# Docker Volume Manager

*Tool to copy docker volume data between running containers and local paths, across ssh*

Often during migrations (ie. migrating bind mounts to docker volumes), you need to copy data between actual docker volumes and local paths. This tool makes it easy to do this.

Doing this manually is slightly cumbersome because you need to either use `docker cp` between the running container which comes with some pitfalls or run `tar` in the container and extract this on the fly on the host. On top of this, you need to manually look up the path of the mounted volumes for each service within your docker-compose file.

## Installation

```bash
pip3 install git+https://github.com/MatthewScholefield/docker-volume-manager
```

## Usage

Run `docker-volume-manager -h` to see the specific CLI usage. You need to provide a `docker-compose.yml` or `.env.*.jsonnet` file along with a folder to copy between (If you are curious about using Jsonnet with docker-compose, see [docker-compose-plus](https://github.com/MatthewScholefield/docker-compose-plus#docker-compose-plus)).
