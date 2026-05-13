import unittest

try:
    from tests.astrbot_lifecycle_helpers import (
        AstrBotLifecycleTests,
        FakeEvent,
        fake_observation,
        fake_request,
    )
    from tests import (
        astrbot_lifecycle_part01 as _astrbot_lifecycle_part01,
        astrbot_lifecycle_part02 as _astrbot_lifecycle_part02,
        astrbot_lifecycle_part03 as _astrbot_lifecycle_part03,
        astrbot_lifecycle_part04 as _astrbot_lifecycle_part04,
        astrbot_lifecycle_part05 as _astrbot_lifecycle_part05,
        astrbot_lifecycle_part06 as _astrbot_lifecycle_part06,
        astrbot_lifecycle_part07 as _astrbot_lifecycle_part07,
        astrbot_lifecycle_part08 as _astrbot_lifecycle_part08,
        astrbot_lifecycle_part09 as _astrbot_lifecycle_part09,
        astrbot_lifecycle_part10 as _astrbot_lifecycle_part10,
        astrbot_lifecycle_part11 as _astrbot_lifecycle_part11,
        astrbot_lifecycle_part12 as _astrbot_lifecycle_part12,
        astrbot_lifecycle_part13 as _astrbot_lifecycle_part13,
        astrbot_lifecycle_part14 as _astrbot_lifecycle_part14,
        astrbot_lifecycle_part15 as _astrbot_lifecycle_part15,
    )
except ModuleNotFoundError:
    from astrbot_lifecycle_helpers import (
        AstrBotLifecycleTests,
        FakeEvent,
        fake_observation,
        fake_request,
    )
    import astrbot_lifecycle_part01 as _astrbot_lifecycle_part01
    import astrbot_lifecycle_part02 as _astrbot_lifecycle_part02
    import astrbot_lifecycle_part03 as _astrbot_lifecycle_part03
    import astrbot_lifecycle_part04 as _astrbot_lifecycle_part04
    import astrbot_lifecycle_part05 as _astrbot_lifecycle_part05
    import astrbot_lifecycle_part06 as _astrbot_lifecycle_part06
    import astrbot_lifecycle_part07 as _astrbot_lifecycle_part07
    import astrbot_lifecycle_part08 as _astrbot_lifecycle_part08
    import astrbot_lifecycle_part09 as _astrbot_lifecycle_part09
    import astrbot_lifecycle_part10 as _astrbot_lifecycle_part10
    import astrbot_lifecycle_part11 as _astrbot_lifecycle_part11
    import astrbot_lifecycle_part12 as _astrbot_lifecycle_part12
    import astrbot_lifecycle_part13 as _astrbot_lifecycle_part13
    import astrbot_lifecycle_part14 as _astrbot_lifecycle_part14
    import astrbot_lifecycle_part15 as _astrbot_lifecycle_part15


_SPLIT_TEST_CLASSES = (
    _astrbot_lifecycle_part01.AstrBotLifecyclePart01,
    _astrbot_lifecycle_part02.AstrBotLifecyclePart02,
    _astrbot_lifecycle_part03.AstrBotLifecyclePart03,
    _astrbot_lifecycle_part04.AstrBotLifecyclePart04,
    _astrbot_lifecycle_part05.AstrBotLifecyclePart05,
    _astrbot_lifecycle_part06.AstrBotLifecyclePart06,
    _astrbot_lifecycle_part07.AstrBotLifecyclePart07,
    _astrbot_lifecycle_part08.AstrBotLifecyclePart08,
    _astrbot_lifecycle_part09.AstrBotLifecyclePart09,
    _astrbot_lifecycle_part10.AstrBotLifecyclePart10,
    _astrbot_lifecycle_part11.AstrBotLifecyclePart11,
    _astrbot_lifecycle_part12.AstrBotLifecyclePart12,
    _astrbot_lifecycle_part13.AstrBotLifecyclePart13,
    _astrbot_lifecycle_part14.AstrBotLifecyclePart14,
    _astrbot_lifecycle_part15.AstrBotLifecyclePart15,
)


def _install_split_tests():
    for test_class in _SPLIT_TEST_CLASSES:
        for name, value in test_class.__dict__.items():
            if name.startswith("test_"):
                setattr(AstrBotLifecycleTests, name, value)


_install_split_tests()


if __name__ == "__main__":
    unittest.main()
