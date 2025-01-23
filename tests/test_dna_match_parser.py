"""Test the DNA match parser."""

from gramps_webapi.api.dna import parse_raw_dna_match_string


def test_gramplet_form():
    """Test the format supported by the Gramplet."""
    string = """Chromosome,Start Location,End Location,Centimorgans,Matching SNPs,Name,Match Name
3,56950055,64247327,10.9,375,Luther Robinson, Robert F. Garner
11,25878681,35508918,9.9,396
"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 2
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 10.9,
        "SNPs": 375,
        "comment": "Luther Robinson",
    }
    assert segments[1] == {
        "chromosome": "11",
        "start": 25878681,
        "stop": 35508918,
        "side": "U",
        "cM": 9.9,
        "SNPs": 396,
        "comment": "",
    }


def test_gramplet_form_with_tabs():
    """Test the format supported by the Gramplet with tabs."""
    string = """Chromosome	Start Location	End Location	Centimorgans	Matching SNPs	Name	Match Name
3	56950055	64247327	10.9	375	Luther Robinson	 Robert F. Garner
11	25878681	35508918	9.9	396
"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 2
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 10.9,
        "SNPs": 375,
        "comment": "Luther Robinson",
    }
    assert segments[1] == {
        "chromosome": "11",
        "start": 25878681,
        "stop": 35508918,
        "side": "U",
        "cM": 9.9,
        "SNPs": 396,
        "comment": "",
    }


def test_gramplet_form_without_header():
    """Test the format supported by the Gramplet without header."""
    string = """3,56950055,64247327,10.9,375,Luther Robinson, Robert F. Garner
11,25878681,35508918,9.9,396
"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 2
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 10.9,
        "SNPs": 375,
        "comment": "Luther Robinson",
    }
    assert segments[1] == {
        "chromosome": "11",
        "start": 25878681,
        "stop": 35508918,
        "side": "U",
        "cM": 9.9,
        "SNPs": 396,
        "comment": "",
    }
