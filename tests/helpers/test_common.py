from easyecs.helpers.common import convert_containers_to_dict


def test_convert_containers_to_dict_keeps_containers_without_runtime_id():
    containers = [{"name": "web"}]

    parsed = convert_containers_to_dict(containers)

    assert parsed == {"web": {"name": "web"}}
