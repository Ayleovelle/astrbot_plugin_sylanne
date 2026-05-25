import unittest

try:
    from tests.public_api_helpers import *
    from tests import (
        public_api_part01 as _public_api_part01,
        public_api_memory_part01 as _public_api_memory_part01,
        public_api_memory_part02 as _public_api_memory_part02,
        public_api_memory_part03 as _public_api_memory_part03,
        public_api_memory_part04 as _public_api_memory_part04,
        public_api_memory_part05 as _public_api_memory_part05,
        public_api_memory_part06 as _public_api_memory_part06,
        public_api_memory_part07 as _public_api_memory_part07,
        public_api_memory_part08 as _public_api_memory_part08,
    )
except ModuleNotFoundError:
    from public_api_helpers import *
    import public_api_part01 as _public_api_part01
    import public_api_memory_part01 as _public_api_memory_part01
    import public_api_memory_part02 as _public_api_memory_part02
    import public_api_memory_part03 as _public_api_memory_part03
    import public_api_memory_part04 as _public_api_memory_part04
    import public_api_memory_part05 as _public_api_memory_part05
    import public_api_memory_part06 as _public_api_memory_part06
    import public_api_memory_part07 as _public_api_memory_part07
    import public_api_memory_part08 as _public_api_memory_part08


_SPLIT_TEST_CLASSES = (
    (PublicApiTests, _public_api_part01.PublicApiPart01),
    (MemoryPayloadPublicApiTests, _public_api_memory_part01.PublicApiMemoryPart01),
    (MemoryPayloadPublicApiTests, _public_api_memory_part02.PublicApiMemoryPart02),
    (MemoryPayloadPublicApiTests, _public_api_memory_part03.PublicApiMemoryPart03),
    (MemoryPayloadPublicApiTests, _public_api_memory_part04.PublicApiMemoryPart04),
    (MemoryPayloadPublicApiTests, _public_api_memory_part05.PublicApiMemoryPart05),
    (MemoryPayloadPublicApiTests, _public_api_memory_part06.PublicApiMemoryPart06),
    (MemoryPayloadPublicApiTests, _public_api_memory_part07.PublicApiMemoryPart07),
    (MemoryPayloadPublicApiTests, _public_api_memory_part08.PublicApiMemoryPart08),
)


def _install_split_tests():
    for base_class, test_class in _SPLIT_TEST_CLASSES:
        for name, value in test_class.__dict__.items():
            if name.startswith("test_"):
                setattr(base_class, name, value)


_install_split_tests()


if __name__ == "__main__":
    unittest.main()
