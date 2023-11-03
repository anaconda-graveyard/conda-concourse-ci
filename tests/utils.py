import os

test_data_dir = os.path.join(os.path.dirname(__file__), "data")
test_config_dir = os.path.join(test_data_dir, "config-test")
graph_data_dir = os.path.join(test_data_dir, "graph_data")

default_worker = {
    "platform": "linux",
    "arch": "64",
    "label": "linux",
    "pool_name": "linux_pool",
}


def make_recipe(name, dependencies=()):
    os.makedirs(name)
    with open(os.path.join(name, "meta.yaml"), "w") as f:
        # not valid meta.yaml.  Doesn't matter for test.
        f.write("package:\n")
        f.write("   name: {0}\n".format(name))
        f.write("   version: 1.0\n")
        if dependencies:
            f.write("requirements:\n")
            f.write("    build:\n")
            for dep in dependencies:
                f.write("        - {0}\n".format(dep))
