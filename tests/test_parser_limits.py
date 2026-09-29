import pytest

from pokeeper.catalog import parse_po
from pokeeper.config import KeeperError


def test_empty_plural_identity_is_rejected_instead_of_silently_collapsed():
    raw = b'msgid "item"\nmsgid_plural ""\nmsgstr[0] "one"\nmsgstr[1] "many"\n'
    with pytest.raises(KeeperError, match="empty or missing msgid_plural"):
        parse_po(raw)
