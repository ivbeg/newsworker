from lxml.html import fromstring

from newsworker.consts import (
    TAG_TYPE_BOLD,
    TAG_TYPE_HREF,
    TAG_TYPE_IMG,
    TAG_TYPE_TAIL,
    TAG_TYPE_TEXT,
    TAG_TYPE_WRAPPER,
)
from newsworker.tagmapper import TagBlock, TagEntry, TagPath


def test_tag_paths_shared_nodes_identity_and_rendering():
    doc = fromstring(
        "<html><body><section><div><span>A</span></div><div><b>B</b></div></section></body></html>"
    )
    left = doc.xpath("//span")[0]
    right = doc.xpath("//b")[0]
    path = TagPath(left)
    same = TagPath(left)
    assert path == same and hash(path) == hash(same)
    assert path != "not-a-path"
    assert path.values() and path.key_values() == path.key
    assert path.tag_names()[-1] == "span"
    assert path.as_xpath().startswith("//html/")
    shared = TagPath.getSharedNode(left, right)
    assert shared.tag == "section"
    assert TagPath.getSharedPath(left, right).tag_names()[-1] == "section"


def test_tag_entry_and_block_entity_annotations(capsys):
    root = fromstring(
        "<main><article><h2><a href='/one'>Headline</a></h2> tail"
        "<div><img src='/image.jpg'></div><script>ignored</script></article>"
        "<article><strong>Second</strong></article></main>"
    )
    entry = TagEntry(1, root, "main", 0, TagPath(root), None)
    assert entry.as_list()[0] == 1 and entry.as_list()[5] == []

    block = TagBlock(root, "path", 0, None)
    block.add_entity("title", "p", TAG_TYPE_TEXT, "Headline", True)
    assert block.get_entities()["title"][2] == "Headline"
    assert block.as_dict()["path"] == "path"
    assert b"article" in block.as_html()
    annotations = block.identify_entities()
    by_tag = {annotation.node.tag: annotation for annotation in annotations}
    assert TAG_TYPE_BOLD in by_tag["h2"].attrs
    assert TAG_TYPE_HREF in by_tag["a"].attrs
    assert TAG_TYPE_TEXT in by_tag["a"].attrs
    assert TAG_TYPE_IMG in by_tag["img"].attrs
    assert TAG_TYPE_WRAPPER in by_tag["div"].attrs
    assert any(TAG_TYPE_TAIL in annotation.attrs for annotation in annotations)
    assert by_tag["a"].parent_id == by_tag["h2"].as_list()[0]
    block.print_block()
    assert b"article" in capsys.readouterr().out.encode()

    shifted = TagBlock(root, "path", 0, 2)
    assert shifted.as_html().count(b"article") >= 2
    assert shifted.identify_entities()
    shifted.print_block()
    assert "article" in capsys.readouterr().out
