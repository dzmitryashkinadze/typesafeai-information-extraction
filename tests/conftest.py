import pytest

from typesafeai_information_extraction_demo.pipeline import ClassicPipeline


@pytest.fixture(scope="session")
def pipeline():
    return ClassicPipeline()
