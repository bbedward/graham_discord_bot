import yaml
import toml

from util.util import Utils
import pathlib
import io

with open(f"{Utils.get_project_root().joinpath(pathlib.PurePath('config.yaml'))}", "r") as in_yaml:
    loaded = yaml.load(in_yaml, Loader=yaml.FullLoader)

print(loaded)