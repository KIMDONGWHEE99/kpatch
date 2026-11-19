"""큰 기술 카드의 설명과 오른쪽 그림 사이에 공간을 확보합니다."""
import hashlib


LAYOUT_EDITS = {
    ("sharedassets1.assets", 806): {
        "type": "RectTransform", "field": "/m_SizeDelta/x", "source": -16.0, "expected": -120.0,
        "source_object_sha256": "86d725380f4eba870629255e8842debae263134d4ef7a97f4031dcb71fb95f26",
    },
    ("sharedassets1.assets", 678): {
        "type": "RectTransform", "field": "/m_SizeDelta/y", "source": 72.0, "expected": 96.0,
        "source_object_sha256": "829feacd728e169507e10eade10a574222245d8827e7359e1f1e3bb00b305207",
    },
    ("sharedassets1.assets", 1022): {
        "type": "MonoBehaviour", "field": "/m_lineSpacing", "source": 20.0, "expected": 0.0,
        "source_object_sha256": "d66ac02b346188d45c0f7428aafa8c83244288d1f4982560aa21bb7c3fec366f",
    },
}


def apply_layout(name, obj, tree):
    """원본 객체와 필드값을 확인한 뒤 지정한 한 필드만 변경합니다."""
    spec = LAYOUT_EDITS.get((name, obj.path_id))
    if spec is None:
        return
    if obj.type.name != spec["type"]:
        raise ValueError(f"기술 카드 객체 형식 불일치: {name}/{obj.path_id}")
    if hashlib.sha256(obj.get_raw_data()).hexdigest() != spec["source_object_sha256"]:
        raise ValueError(f"기술 카드 원본 객체 해시 불일치: {name}/{obj.path_id}")
    keys = spec["field"].strip("/").split("/")
    target = tree
    for key in keys[:-1]:
        target = target[key]
    if target[keys[-1]] != spec["source"]:
        raise ValueError(f"기술 카드 원본 필드 불일치: {name}/{obj.path_id}{spec['field']}")
    target[keys[-1]] = spec["expected"]
