"""Test the DNA match parser."""

from gramps_webapi.api.dna import cast_float, parse_raw_dna_match_string


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


def test_myheritage_format():
    """Test the MyHeritage CSV format."""
    string = """Name,Match Name,Chromosome,Start Location,End Location,Start RSID,End RSID,Centimorgans,SNPs
John Doe,Jane Doe,10,11830498,29606974,rs7924203,rs11007524,27.7,11520
John Doe,Jane Doe,10,50018165,82402437,rs2928402,rs4934387,36.6,17920"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 2
    assert segments[0] == {
        "chromosome": "10",
        "start": 11830498,
        "stop": 29606974,
        "side": "U",
        "cM": 27.7,
        "SNPs": 11520,
        "comment": "John Doe",
    }
    assert segments[1] == {
        "chromosome": "10",
        "start": 50018165,
        "stop": 82402437,
        "side": "U",
        "cM": 36.6,
        "SNPs": 17920,
        "comment": "John Doe",
    }


def test_gedmatch_german_locale():
    """Test the Gedmatch CSV format with German locale."""
    string = """Chr 	B37 Start Pos'n	B37 End Pos'n	Centimorgans (cM)	SNPs 	Segment threshold	Bunch limit	SNP Density Ratio
11	69.231.796	83.487.889	15,5	2.157	210	126	0,29
11	130.347.190	133.862.526	11,1	977	204	122	0,34"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 2
    assert segments[0] == {
        "chromosome": "11",
        "start": 69231796,
        "stop": 83487889,
        "side": "U",
        "cM": 15.5,
        "SNPs": 2157,
        "comment": "210",
    }
    assert segments[1] == {
        "chromosome": "11",
        "start": 130347190,
        "stop": 133862526,
        "side": "U",
        "cM": 11.1,
        "SNPs": 977,
        "comment": "204",
    }


def test_geneatnet_format():
    """Test the GeneaNet CSV format."""
    string = """Chromosome;Start of segment;Length of segment;Number of SNPs;Length in centimorgan (cM);Type of segment
9;14037831;73101159;6804;38.64;half-identical
"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "9",
        "start": 14037831,
        "stop": 73101159,
        "side": "U",
        "cM": 38.64,
        "SNPs": 6804,
        "comment": "half-identical",
    }


def test_with_whitespace():
    """Test a wrong format."""
    string = """
        Chromosome,   Start\t, End, \tcM
        3, 56950055, 64247327, 10.9"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 10.9,
        "SNPs": 0,
        "comment": "",
    }


def test_three_columns():
    """Test a wrong format."""
    string = """Chromosome,Start Location,End Location
3,56950055,64247327"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 0


def test_integer_with_separators():
    """Test a wrong format."""
    string = """Chromosome,Start Location,End Location,Centimorgans
3,56.950.055,64.247.327,10.9"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 10.9,
        "SNPs": 0,
        "comment": "",
    }


def test_integer_with_separators_tab():
    """Test a wrong format."""
    string = """Chromosome\tStart Location\tEnd Location\tCentimorgans
3\t56,950,055\t64,247,327\t10.9"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 10.9,
        "SNPs": 0,
        "comment": "",
    }


def test_non_castable_integer():
    """Test a wrong format."""
    string = """Chromosome,Start Location,End Location,Centimorgans
3,56950055,64247327a,10.9"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 0,
        "side": "U",
        "cM": 10.9,
        "SNPs": 0,
        "comment": "",
    }


def test_non_castable_float():
    """Test a wrong format."""
    string = """Chromosome,Start Location,End Location,Centimorgans
3,56950055,64247327,10.9a"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 0,
        "SNPs": 0,
        "comment": "",
    }


def test_cast_float_mixed_separators():
    """Test cast_float with mixed thousands and decimal separators.

    A value combining a thousands separator and a decimal separator (e.g.
    the European "1.234,56" or the US "1,234.56") was not handled by any of
    the existing branches and silently fell back to 0.0. The rightmost
    separator is the decimal separator; the other groups thousands.
    """
    # European grouping: "." thousands, "," decimal
    assert cast_float("1.234,56") == 1234.56
    assert cast_float("1.234.567,89") == 1234567.89
    # US/UK grouping: "," thousands, "." decimal
    assert cast_float("1,234.56") == 1234.56
    assert cast_float("1,234,567.89") == 1234567.89
    # Existing single-separator behaviour must be preserved
    assert cast_float("15,5") == 15.5
    assert cast_float("38.64") == 38.64
    assert cast_float("1.234.567") == 1234567.0
    assert cast_float("1,234,567") == 1234567.0


def test_mixed_separator_centimorgans():
    """Test parsing a table whose centimorgans use mixed separators.

    Guards against the regression where a centimorgans value formatted with
    both a thousands and a decimal separator was parsed as 0.0.
    """
    string = """Chromosome;Start Location;End Location;Centimorgans
3;56950055;64247327;1.234,56"""
    segments = parse_raw_dna_match_string(string)
    assert len(segments) == 1
    assert segments[0] == {
        "chromosome": "3",
        "start": 56950055,
        "stop": 64247327,
        "side": "U",
        "cM": 1234.56,
        "SNPs": 0,
        "comment": "",
    }
