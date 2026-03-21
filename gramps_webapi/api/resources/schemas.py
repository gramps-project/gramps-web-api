"""Response schemas for the Gramps Web API.

Each class defines the shape of a response object and is used exclusively for
OpenAPI documentation via flask-smorest ``@api_blueprint.response()``; they do
**not** perform serialisation because most endpoints return a pre-built Flask
``Response`` object that flask-smorest passes through unchanged.

All schemas set ``Meta.unknown = INCLUDE`` so that no data is silently dropped
if one of these schemas is accidentally used for de-serialisation, and to avoid
breaking if Gramps adds new fields.

Dependency order (leaf → root) is maintained so that forward-reference lambdas
are needed only for genuinely circular pairs.
"""

from marshmallow import INCLUDE, Schema, fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Base(Schema):
    """Base class that tolerates unknown keys (doc-only schemas)."""

    class Meta:
        unknown = INCLUDE


# ===========================================================================
# 1. Leaf / primitive schemas
# ===========================================================================


class DateSchema(_Base):
    """A Gramps date object."""

    calendar = fields.Int(
        metadata={"description": "The calendar format for the date."},
    )
    dateval = fields.List(
        fields.Raw(),
        metadata={"description": "Mixed array of integers and booleans."},
    )
    modifier = fields.Int(
        metadata={"description": "Date modifier (e.g. before/after/about)."},
    )
    newyear = fields.Int(
        metadata={"description": "Alternate new-year start."},
    )
    quality = fields.Int(
        metadata={"description": "Quality / confidence of the date."},
    )
    sortval = fields.Int(
        metadata={"description": "Value used for date sorting."},
    )
    text = fields.Str(
        metadata={"description": "Textual representation of the date."},
    )
    year = fields.Int(
        metadata={"description": "Year component of the date."},
    )


class StyledTextTagSchema(_Base):
    """A formatting tag applied to a range of styled text."""

    name = fields.Str(
        metadata={"description": "Name of the tag (e.g. 'Bold', 'Italic')."},
    )
    value = fields.Raw(
        metadata={"description": "Value of the tag; may be null, string, or integer."},
    )
    ranges = fields.List(
        fields.List(fields.Int()),
        metadata={"description": "List of [start, end] character-offset pairs."},
    )


class StyledTextSchema(_Base):
    """A block of text with inline formatting tags."""

    string = fields.Str(
        metadata={"description": "The plain text content."},
    )
    tags = fields.List(
        fields.Nested(StyledTextTagSchema),
        metadata={
            "description": "List of formatting tags applied to spans of the text."
        },
    )


class URLSchema(_Base):
    """A URL associated with a Gramps object."""

    desc = fields.Str(
        metadata={"description": "Description of the URL."},
    )
    path = fields.Str(
        metadata={"description": "The URL itself."},
    )
    private = fields.Bool(
        metadata={"description": "Private object indicator."},
    )
    type = fields.Str(
        metadata={"description": "Type of URL (e.g. 'Web Home')."},
    )


class LocationSchema(_Base):
    """An alternate location description (no date, no citation list)."""

    city = fields.Str(metadata={"description": "City."})
    country = fields.Str(metadata={"description": "Country."})
    county = fields.Str(metadata={"description": "County."})
    locality = fields.Str(metadata={"description": "Locality."})
    parish = fields.Str(metadata={"description": "Parish."})
    phone = fields.Str(metadata={"description": "Phone number."})
    postal = fields.Str(metadata={"description": "Postal code."})
    state = fields.Str(metadata={"description": "State."})
    street = fields.Str(metadata={"description": "Street address."})


class AttributeSchema(_Base):
    """An attribute (typed key/value pair) with supporting citations and notes."""

    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this attribute."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes about this attribute."},
    )
    private = fields.Bool(
        metadata={"description": "Private object indicator."},
    )
    type = fields.Str(
        metadata={"description": "Type of the attribute."},
    )
    value = fields.Str(
        metadata={"description": "Value of the attribute."},
    )


class SurnameSchema(_Base):
    """A single surname entry within a Name object."""

    connector = fields.Str(
        metadata={"description": "Connector word between given name and surname."},
    )
    origintype = fields.Str(
        metadata={"description": "Name origin type (e.g. 'Inherited')."},
    )
    prefix = fields.Str(
        metadata={"description": "Surname prefix (e.g. 'von', 'de')."},
    )
    primary = fields.Bool(
        metadata={"description": "Whether this is the primary surname."},
    )
    surname = fields.Str(
        metadata={"description": "The surname text."},
    )


class AddressSchema(_Base):
    """A postal address, optionally dated."""

    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this address."},
    )
    city = fields.Str(metadata={"description": "City."})
    country = fields.Str(metadata={"description": "Country."})
    county = fields.Str(metadata={"description": "County."})
    date = fields.Nested(
        DateSchema,
        metadata={"description": "Date the person resided at this address."},
    )
    locality = fields.Str(metadata={"description": "Locality."})
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes about this address."},
    )
    phone = fields.Str(metadata={"description": "Phone number."})
    postal = fields.Str(metadata={"description": "Postal code."})
    private = fields.Bool(metadata={"description": "Private object indicator."})
    state = fields.Str(metadata={"description": "State."})
    street = fields.Str(metadata={"description": "Street address."})


# ===========================================================================
# 2. Name-related schemas
# ===========================================================================


class PlaceNameSchema(_Base):
    """A place name with optional date and language."""

    date = fields.Nested(
        DateSchema,
        metadata={"description": "Period during which this name was in use."},
    )
    lang = fields.Str(
        metadata={"description": "Language the name is in."},
    )
    value = fields.Str(
        metadata={"description": "The place name text."},
    )


class PlaceReferenceSchema(_Base):
    """A reference to a parent place with an optional date."""

    date = fields.Nested(
        DateSchema,
        metadata={"description": "Date of the place reference."},
    )
    ref = fields.Str(
        metadata={"description": "Handle of the referenced place."},
    )


class LDSOrdinationSchema(_Base):
    """An LDS church ordinance event."""

    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this LDS event."},
    )
    date = fields.Nested(
        DateSchema,
        metadata={"description": "Date of the ordinance."},
    )
    famc = fields.Str(
        metadata={
            "description": "Handle of the family associated with this ordinance."
        },
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes about this ordinance."},
    )
    place = fields.Str(
        metadata={
            "description": "Handle of the place where the ordinance was performed."
        },
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    status = fields.Int(
        metadata={"description": "Status code of the ordinance."},
    )
    temple = fields.Str(
        metadata={"description": "Temple where the ordinance was performed."},
    )
    type = fields.Int(
        metadata={"description": "Type code of the ordinance."},
    )


class NameSchema(_Base):
    """A complete name record (primary or alternate)."""

    call = fields.Str(
        metadata={"description": "Call name (the name by which the person is known)."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this name."},
    )
    date = fields.Nested(
        DateSchema,
        metadata={"description": "Period during which this name was in use."},
    )
    display_as = fields.Int(
        metadata={"description": "Identifier for how to display the name."},
    )
    famnick = fields.Str(
        metadata={"description": "Family nickname."},
    )
    first_name = fields.Str(
        metadata={"description": "Given (first) name."},
    )
    group_as = fields.Str(
        metadata={"description": "Override for grouping this name."},
    )
    nick = fields.Str(
        metadata={"description": "Nickname."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes about this name."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    sort_as = fields.Int(
        metadata={"description": "Identifier for how to sort the name."},
    )
    suffix = fields.Str(
        metadata={"description": "Name suffix (e.g. 'Sr', 'Jr')."},
    )
    surname_list = fields.List(
        fields.Nested(SurnameSchema),
        metadata={"description": "List of surname components."},
    )
    title = fields.Str(
        metadata={"description": "Name title or prefix (e.g. 'Dr.', 'Rev.')."},
    )
    type = fields.Str(
        metadata={"description": "Type of name (e.g. 'Birth Name', 'Also Known As')."},
    )


# ===========================================================================
# 3. Profile schemas  (circular — use lambdas where needed)
# ===========================================================================


class EventProfileSchema(_Base):
    """A summary of a Gramps event, used within profile responses."""

    citations = fields.Int(
        metadata={"description": "Total number of citations supporting this event."},
    )
    confidence = fields.Int(
        metadata={
            "description": "Highest confidence rating among the supporting citations."
        },
    )
    date = fields.Str(
        metadata={"description": "Date of the event as a formatted string."},
    )
    place = fields.Str(
        metadata={"description": "Name of the place where the event occurred."},
    )
    place_name = fields.Str(
        metadata={"description": "Short name of the event place."},
    )
    type = fields.Str(
        metadata={"description": "Type of the event (e.g. 'Birth', 'Death')."},
    )
    participants = fields.Dict(
        metadata={"description": "People and families participating in this event."},
    )
    references = fields.Dict(
        metadata={"description": "References to this event from other objects."},
    )


class PersonProfileSchema(_Base):
    """A summary of a person's key biographical information."""

    birth = fields.Nested(
        EventProfileSchema,
        metadata={"description": "Birth event profile (or best available fallback)."},
    )
    death = fields.Nested(
        EventProfileSchema,
        metadata={"description": "Death event profile (or best available fallback)."},
    )
    events = fields.List(
        fields.Nested(EventProfileSchema),
        metadata={"description": "All event profiles for this person."},
    )
    families = fields.List(
        fields.Nested(lambda: FamilyProfileSchema()),
        metadata={"description": "Profiles of families this person is a parent of."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the person."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the person."},
    )
    name_display = fields.Str(
        metadata={"description": "Full display name."},
    )
    name_given = fields.Str(
        metadata={"description": "Given (first) name."},
    )
    name_surname = fields.Str(
        metadata={"description": "Surname."},
    )
    name_suffix = fields.Str(
        metadata={"description": "Name suffix."},
    )
    other_parent_families = fields.List(
        fields.Nested(lambda: FamilyProfileSchema()),
        metadata={"description": "Profiles of non-primary parent families."},
    )
    primary_parent_family = fields.Nested(
        lambda: FamilyProfileSchema(),
        metadata={"description": "Profile of the primary parent family."},
    )
    references = fields.Dict(
        metadata={"description": "References to this person from other objects."},
    )
    sex = fields.Str(
        metadata={"description": "Sex of the person ('M', 'F', or 'U')."},
    )


class FamilyProfileSchema(_Base):
    """A summary of a family unit."""

    children = fields.List(
        fields.Nested(PersonProfileSchema),
        metadata={"description": "Profiles of children in the family."},
    )
    divorce = fields.Nested(
        EventProfileSchema,
        metadata={"description": "Divorce event profile (or best available fallback)."},
    )
    events = fields.List(
        fields.Nested(EventProfileSchema),
        metadata={"description": "All event profiles for this family."},
    )
    family_surname = fields.Str(
        metadata={
            "description": "Surname of the family (from father, or mother if no father)."
        },
    )
    father = fields.Nested(
        PersonProfileSchema,
        metadata={"description": "Profile of the father."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the family."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the family."},
    )
    marriage = fields.Nested(
        EventProfileSchema,
        metadata={
            "description": "Marriage event profile (or best available fallback)."
        },
    )
    mother = fields.Nested(
        PersonProfileSchema,
        metadata={"description": "Profile of the mother."},
    )
    references = fields.Dict(
        metadata={"description": "References to this family from other objects."},
    )
    relationship = fields.Str(
        metadata={"description": "Type of relationship between the parents."},
    )


class PlaceProfileSchema(_Base):
    """A summary of place information including hierarchy."""

    alternate_names = fields.List(
        fields.Str(),
        metadata={"description": "Alternate names of the place."},
    )
    alternate_place_names = fields.List(
        fields.Raw(),
        metadata={"description": "Alternate names with associated dates."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the place."},
    )
    lat = fields.Float(
        metadata={"description": "Geographic latitude."},
    )
    long = fields.Float(
        metadata={"description": "Geographic longitude."},
    )
    name = fields.Str(
        metadata={"description": "Place title."},
    )
    parent_places = fields.List(
        fields.Nested(lambda: PlaceProfileSchema()),
        metadata={"description": "List of parent place profiles."},
    )
    direct_parent_places = fields.List(
        fields.Raw(),
        metadata={"description": "Direct parent places with corresponding dates."},
    )
    references = fields.Dict(
        metadata={"description": "References to this place from other objects."},
    )


class SourceProfileSchema(_Base):
    """A summary of a source record."""

    author = fields.Str(
        metadata={"description": "Author of the source."},
    )
    pubinfo = fields.Str(
        metadata={"description": "Publication information."},
    )
    title = fields.Str(
        metadata={"description": "Title of the source."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the source."},
    )
    references = fields.Dict(
        metadata={"description": "References to this source from other objects."},
    )


class CitationProfileSchema(_Base):
    """A summary of a citation record."""

    date = fields.Str(
        metadata={"description": "Date of the citation as a formatted string."},
    )
    page = fields.Str(
        metadata={"description": "Page cited from."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the citation."},
    )
    source = fields.Nested(
        SourceProfileSchema,
        metadata={"description": "Profile of the cited source."},
    )
    references = fields.Dict(
        metadata={"description": "References to this citation from other objects."},
    )


class MediaProfileSchema(_Base):
    """A summary of a media object."""

    date = fields.Str(
        metadata={"description": "Date of the media item as a formatted string."},
    )
    gramps_id = fields.Str(
        metadata={
            "description": "Alternate user-managed identifier for the media object."
        },
    )
    references = fields.Dict(
        metadata={"description": "References to this media item from other objects."},
    )


# ===========================================================================
# 4. Reference schemas
# ===========================================================================


class EventReferenceSchema(_Base):
    """A reference from a person or family to an event, including role."""

    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={
            "description": "Attributes related to the person's role in the event."
        },
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes about this participation."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    ref = fields.Str(
        metadata={"description": "Handle of the referenced event."},
    )
    role = fields.Str(
        metadata={"description": "Role of the person or family in the event."},
    )


class MediaReferenceSchema(_Base):
    """A reference to a media object, optionally with a crop rectangle."""

    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes related to this media reference."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of citations supporting this media reference."
        },
    )
    note_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of research notes about this media reference."
        },
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    rect = fields.List(
        fields.Float(),
        metadata={
            "description": "Crop rectangle [left, top, right, bottom] as percentages."
        },
    )
    ref = fields.Str(
        metadata={"description": "Handle of the referenced media object."},
    )


class PersonReferenceSchema(_Base):
    """A reference to another person (e.g. association/relationship)."""

    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this association."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes about this association."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    ref = fields.Str(
        metadata={"description": "Handle of the referenced person."},
    )
    rel = fields.Str(
        metadata={"description": "Relationship type between the two people."},
    )


class RepositoryReferenceSchema(_Base):
    """A reference to a repository where a source can be found."""

    call_number = fields.Str(
        metadata={"description": "Call number for the source at the repository."},
    )
    media_type = fields.Str(
        metadata={"description": "Media format of the source at the repository."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of research notes about this repository reference."
        },
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    ref = fields.Str(
        metadata={"description": "Handle of the referenced repository."},
    )


class ChildReferenceSchema(_Base):
    """A reference to a child within a family."""

    citation_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of citations supporting this child reference."
        },
    )
    frel = fields.Str(
        metadata={"description": "Relationship between the child and the father."},
    )
    mrel = fields.Str(
        metadata={"description": "Relationship between the child and the mother."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of research notes about this child reference."
        },
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    ref = fields.Str(
        metadata={"description": "Handle of the referenced child (person)."},
    )


# ===========================================================================
# 5. Backlinks schemas
# ===========================================================================


class BacklinksSchema(_Base):
    """A map of object-type → list of handles for objects that refer to this object."""

    person = fields.List(
        fields.Str(),
        metadata={"description": "Handles of people referring to this object."},
    )
    family = fields.List(
        fields.Str(),
        metadata={"description": "Handles of families referring to this object."},
    )
    event = fields.List(
        fields.Str(),
        metadata={"description": "Handles of events referring to this object."},
    )
    place = fields.List(
        fields.Str(),
        metadata={"description": "Handles of places referring to this object."},
    )
    source = fields.List(
        fields.Str(),
        metadata={"description": "Handles of sources referring to this object."},
    )
    citation = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations referring to this object."},
    )
    media = fields.List(
        fields.Str(),
        metadata={"description": "Handles of media items referring to this object."},
    )


# ===========================================================================
# 6. Primary object schemas (forward-declared; extended schemas follow)
# ===========================================================================


class TagSchema(_Base):
    """A Gramps tag (label) that can be attached to primary objects."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Tag'."},
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    color = fields.Str(
        metadata={"description": "Colour of the tag as a hex string."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the tag."},
    )
    name = fields.Str(
        metadata={"description": "Tag name."},
    )
    priority = fields.Int(
        metadata={"description": "Display priority of the tag."},
    )


class NoteSchema(_Base):
    """A Gramps note object."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Note'."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={"description": "Objects referring to this note, grouped by type."},
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    format = fields.Int(
        metadata={"description": "Format identifier (0=plain text, 1=pre-formatted)."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the note."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this note."},
    )
    text = fields.Nested(
        StyledTextSchema,
        metadata={"description": "The note text with optional inline formatting."},
    )
    type = fields.Str(
        metadata={"description": "Type of note (e.g. 'Source text', 'General')."},
    )


class MediaSchema(_Base):
    """A Gramps media object (image, document, etc.)."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Media'."},
    )
    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes of the media object."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={
            "description": "Objects referring to this media item, grouped by type."
        },
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    checksum = fields.Str(
        metadata={"description": "Checksum for file integrity validation."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this media object."},
    )
    date = fields.Nested(
        DateSchema,
        metadata={"description": "Date associated with the media object."},
    )
    desc = fields.Str(
        metadata={"description": "Description of the media object content."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the media object."},
    )
    mime = fields.Str(
        metadata={"description": "MIME type of the file (e.g. 'image/jpeg')."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of research notes related to this media object."
        },
    )
    path = fields.Str(
        metadata={"description": "Storage path to locate the media file."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        MediaProfileSchema,
        metadata={"description": "Optional summary of media information."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this media object."},
    )


class RepositorySchema(_Base):
    """A Gramps repository (library, archive, etc.)."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Repository'."},
    )
    address_list = fields.List(
        fields.Nested(AddressSchema),
        metadata={"description": "Addresses of the repository."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={
            "description": "Objects referring to this repository, grouped by type."
        },
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the repository."},
    )
    name = fields.Str(
        metadata={"description": "Name of the repository."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of research notes related to this repository."
        },
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this repository."},
    )
    type = fields.Str(
        metadata={"description": "Type of repository (e.g. 'Library', 'Archive')."},
    )
    urls = fields.List(
        fields.Nested(URLSchema),
        metadata={"description": "URLs associated with this repository."},
    )


class SourceSchema(_Base):
    """A Gramps source record."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Source'."},
    )
    abbrev = fields.Str(
        metadata={"description": "Abbreviated name for the source."},
    )
    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes about the source."},
    )
    author = fields.Str(
        metadata={"description": "Author of the source."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={"description": "Objects referring to this source, grouped by type."},
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the source."},
    )
    media_list = fields.List(
        fields.Nested(MediaReferenceSchema),
        metadata={"description": "Media references associated with this source."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes related to this source."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        SourceProfileSchema,
        metadata={"description": "Optional summary of source information."},
    )
    pubinfo = fields.Str(
        metadata={"description": "Publication information."},
    )
    reporef_list = fields.List(
        fields.Nested(RepositoryReferenceSchema),
        metadata={"description": "References to repositories holding this source."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this source."},
    )
    title = fields.Str(
        metadata={"description": "Title of the source."},
    )


class CitationSchema(_Base):
    """A Gramps citation (a specific use of a source)."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Citation'."},
    )
    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes about this citation."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={
            "description": "Objects referring to this citation, grouped by type."
        },
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    confidence = fields.Int(
        metadata={"description": "Confidence level of the information cited (0–4)."},
    )
    date = fields.Nested(
        DateSchema,
        metadata={"description": "Date of the citation."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the citation."},
    )
    media_list = fields.List(
        fields.Nested(MediaReferenceSchema),
        metadata={"description": "Media references associated with this citation."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes related to this citation."},
    )
    page = fields.Str(
        metadata={"description": "Page or location within the source."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        CitationProfileSchema,
        metadata={"description": "Optional summary of citation information."},
    )
    source_handle = fields.Str(
        metadata={"description": "Handle of the source being cited."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this citation."},
    )


class PlaceSchema(_Base):
    """A Gramps place record."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Place'."},
    )
    alt_loc = fields.List(
        fields.Nested(LocationSchema),
        metadata={"description": "Alternate location descriptions for this place."},
    )
    alt_names = fields.List(
        fields.Nested(PlaceNameSchema),
        metadata={"description": "Alternate names for this place."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={"description": "Objects referring to this place, grouped by type."},
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this place."},
    )
    code = fields.Str(
        metadata={"description": "Place code (e.g. postal code)."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the place."},
    )
    lat = fields.Str(
        metadata={"description": "Latitude as a decimal string."},
    )
    long = fields.Str(
        metadata={"description": "Longitude as a decimal string."},
    )
    media_list = fields.List(
        fields.Nested(MediaReferenceSchema),
        metadata={"description": "Media references associated with this place."},
    )
    name = fields.Nested(
        PlaceNameSchema,
        metadata={"description": "Primary name of the place."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes related to this place."},
    )
    place_type = fields.Str(
        metadata={"description": "Type of place (e.g. 'City', 'Country')."},
    )
    placeref_list = fields.List(
        fields.Nested(PlaceReferenceSchema),
        metadata={"description": "References to parent places."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        PlaceProfileSchema,
        metadata={"description": "Optional summary of place information."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this place."},
    )
    title = fields.Str(
        metadata={"description": "Full place title (e.g. 'Twin Falls, ID, USA')."},
    )
    urls = fields.List(
        fields.Nested(URLSchema),
        metadata={"description": "URLs associated with this place."},
    )


class EventSchema(_Base):
    """A Gramps event record."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Event'."},
    )
    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes about this event."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={"description": "Objects referring to this event, grouped by type."},
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this event."},
    )
    date = fields.Nested(
        DateSchema,
        metadata={"description": "Date of the event."},
    )
    description = fields.Str(
        metadata={"description": "Description of the event."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the event."},
    )
    media_list = fields.List(
        fields.Nested(MediaReferenceSchema),
        metadata={"description": "Media references associated with this event."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes related to this event."},
    )
    place = fields.Str(
        metadata={"description": "Handle of the place where the event occurred."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        EventProfileSchema,
        metadata={"description": "Optional summary of event information."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this event."},
    )
    type = fields.Str(
        metadata={"description": "Type of event (e.g. 'Birth', 'Marriage')."},
    )


class FamilySchema(_Base):
    """A Gramps family record."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Family'."},
    )
    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes about this family."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={"description": "Objects referring to this family, grouped by type."},
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    child_ref_list = fields.List(
        fields.Nested(ChildReferenceSchema),
        metadata={"description": "References to children in this family."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this family."},
    )
    event_ref_list = fields.List(
        fields.Nested(EventReferenceSchema),
        metadata={"description": "References to events the family participated in."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    father_handle = fields.Str(
        metadata={"description": "Handle of the father."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the family."},
    )
    lds_ord_list = fields.List(
        fields.Nested(LDSOrdinationSchema),
        metadata={"description": "LDS ordinance events for this family."},
    )
    media_list = fields.List(
        fields.Nested(MediaReferenceSchema),
        metadata={"description": "Media references associated with this family."},
    )
    mother_handle = fields.Str(
        metadata={"description": "Handle of the mother."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes related to this family."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        FamilyProfileSchema,
        metadata={"description": "Optional summary of family information."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this family."},
    )
    type = fields.Str(
        metadata={
            "description": "Relationship type between the parents (e.g. 'Married')."
        },
    )


class PersonSchema(_Base):
    """A Gramps person record."""

    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name; must be 'Person'."},
    )
    address_list = fields.List(
        fields.Nested(AddressSchema),
        metadata={"description": "Addresses associated with this person."},
    )
    alternate_names = fields.List(
        fields.Nested(NameSchema),
        metadata={"description": "Alternate names used by this person."},
    )
    attribute_list = fields.List(
        fields.Nested(AttributeSchema),
        metadata={"description": "Attributes about this person."},
    )
    backlinks = fields.Nested(
        BacklinksSchema,
        metadata={"description": "Objects referring to this person, grouped by type."},
    )
    birth_ref_index = fields.Int(
        metadata={
            "description": "Index into event_ref_list for the birth event, or -1."
        },
    )
    change = fields.Float(
        metadata={"description": "Unix timestamp of the last modification."},
    )
    citation_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of citations supporting this person."},
    )
    death_ref_index = fields.Int(
        metadata={
            "description": "Index into event_ref_list for the death event, or -1."
        },
    )
    event_ref_list = fields.List(
        fields.Nested(EventReferenceSchema),
        metadata={"description": "References to events this person participated in."},
    )
    extended = fields.Raw(
        metadata={
            "description": "Optional extended section with full referenced records."
        },
    )
    family_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of families this person is a parent of."},
    )
    gender = fields.Int(
        metadata={"description": "Gender code (0=unknown, 1=male, 2=female)."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the person."},
    )
    lds_ord_list = fields.List(
        fields.Nested(LDSOrdinationSchema),
        metadata={"description": "LDS ordinance events for this person."},
    )
    media_list = fields.List(
        fields.Nested(MediaReferenceSchema),
        metadata={"description": "Media references associated with this person."},
    )
    note_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of research notes related to this person."},
    )
    parent_family_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of families this person is a child of."},
    )
    person_ref_list = fields.List(
        fields.Nested(PersonReferenceSchema),
        metadata={
            "description": "References to other people this person has a relationship with."
        },
    )
    primary_name = fields.Nested(
        NameSchema,
        metadata={"description": "Primary name of this person."},
    )
    private = fields.Bool(metadata={"description": "Private object indicator."})
    profile = fields.Nested(
        PersonProfileSchema,
        metadata={"description": "Optional summary of key biographical information."},
    )
    tag_list = fields.List(
        fields.Str(),
        metadata={"description": "Handles of tags attached to this person."},
    )
    urls = fields.List(
        fields.Nested(URLSchema),
        metadata={"description": "URLs associated with this person."},
    )


# ===========================================================================
# 7. Extended schemas
# ===========================================================================


class BacklinksExtendedSchema(_Base):
    """Full object records for each referring object, grouped by type."""

    person = fields.List(
        fields.Nested(PersonSchema),
        metadata={"description": "Full person records referring to this object."},
    )
    family = fields.List(
        fields.Nested(FamilySchema),
        metadata={"description": "Full family records referring to this object."},
    )
    event = fields.List(
        fields.Nested(EventSchema),
        metadata={"description": "Full event records referring to this object."},
    )
    place = fields.List(
        fields.Nested(PlaceSchema),
        metadata={"description": "Full place records referring to this object."},
    )
    source = fields.List(
        fields.Nested(SourceSchema),
        metadata={"description": "Full source records referring to this object."},
    )
    citation = fields.List(
        fields.Nested(CitationSchema),
        metadata={"description": "Full citation records referring to this object."},
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records referring to this object."},
    )


class NoteExtendedSchema(_Base):
    """Extended section of a note response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={"description": "Full records for objects referring to this note."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class MediaExtendedSchema(_Base):
    """Extended section of a media response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={
            "description": "Full records for objects referring to this media item."
        },
    )
    citations = fields.List(
        fields.Nested(CitationSchema),
        metadata={"description": "Full citation records for referenced citations."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class RepositoryExtendedSchema(_Base):
    """Extended section of a repository response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={
            "description": "Full records for objects referring to this repository."
        },
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class SourceExtendedSchema(_Base):
    """Extended section of a source response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={"description": "Full records for objects referring to this source."},
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records for referenced media objects."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    repositories = fields.List(
        fields.Nested(RepositorySchema),
        metadata={
            "description": "Full repository records for referenced repositories."
        },
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class CitationExtendedSchema(_Base):
    """Extended section of a citation response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={
            "description": "Full records for objects referring to this citation."
        },
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records for referenced media objects."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    source = fields.Nested(
        SourceSchema,
        metadata={"description": "Full source record for the cited source."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class PlaceExtendedSchema(_Base):
    """Extended section of a place response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={"description": "Full records for objects referring to this place."},
    )
    citations = fields.List(
        fields.Nested(CitationSchema),
        metadata={"description": "Full citation records for referenced citations."},
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records for referenced media objects."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class EventExtendedSchema(_Base):
    """Extended section of an event response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={"description": "Full records for objects referring to this event."},
    )
    citations = fields.List(
        fields.Nested(CitationSchema),
        metadata={"description": "Full citation records for referenced citations."},
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records for referenced media objects."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    place = fields.Nested(
        PlaceSchema,
        metadata={"description": "Full place record if a place was referenced."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class FamilyExtendedSchema(_Base):
    """Extended section of a family response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={"description": "Full records for objects referring to this family."},
    )
    children = fields.List(
        fields.Nested(PersonSchema),
        metadata={"description": "Full person records for children."},
    )
    citations = fields.List(
        fields.Nested(CitationSchema),
        metadata={"description": "Full citation records for referenced citations."},
    )
    events = fields.List(
        fields.Nested(EventSchema),
        metadata={"description": "Full event records for referenced events."},
    )
    father = fields.Nested(
        PersonSchema,
        metadata={"description": "Full person record for the father."},
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records for referenced media objects."},
    )
    mother = fields.Nested(
        PersonSchema,
        metadata={"description": "Full person record for the mother."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


class PersonExtendedSchema(_Base):
    """Extended section of a person response."""

    backlinks = fields.Nested(
        BacklinksExtendedSchema,
        metadata={"description": "Full records for objects referring to this person."},
    )
    citations = fields.List(
        fields.Nested(CitationSchema),
        metadata={"description": "Full citation records for referenced citations."},
    )
    events = fields.List(
        fields.Nested(EventSchema),
        metadata={"description": "Full event records for referenced events."},
    )
    families = fields.List(
        fields.Nested(FamilySchema),
        metadata={
            "description": "Full family records for families this person is a parent of."
        },
    )
    media = fields.List(
        fields.Nested(MediaSchema),
        metadata={"description": "Full media records for referenced media objects."},
    )
    notes = fields.List(
        fields.Nested(NoteSchema),
        metadata={"description": "Full note records for referenced notes."},
    )
    parent_families = fields.List(
        fields.Nested(FamilySchema),
        metadata={"description": "Full family records for parent families."},
    )
    people = fields.List(
        fields.Nested(PersonSchema),
        metadata={"description": "Full person records for referenced people."},
    )
    primary_parent_family = fields.Nested(
        FamilySchema,
        metadata={"description": "Full family record for the primary parent family."},
    )
    tags = fields.List(
        fields.Nested(TagSchema),
        metadata={"description": "Full tag records for referenced tags."},
    )


# ===========================================================================
# 8. Misc response schemas
# ===========================================================================


class JWTAccessTokensSchema(_Base):
    """Response containing both an access token and a refresh token."""

    access_token = fields.Str(
        metadata={"description": "JWT access token."},
    )
    refresh_token = fields.Str(
        metadata={"description": "JWT refresh token."},
    )


class JWTRefreshTokenSchema(_Base):
    """Response containing a new access token (from a refresh)."""

    access_token = fields.Str(
        metadata={"description": "New JWT access token."},
    )


class JWTAccessTokenSchema(_Base):
    """Response containing only an access token."""

    access_token = fields.Str(
        metadata={"description": "JWT access token."},
    )


class OIDCProviderSchema(_Base):
    """An available OIDC authentication provider."""

    id = fields.Str(
        metadata={"description": "Provider identifier (e.g. 'google')."},
    )
    name = fields.Str(
        metadata={"description": "Human-readable provider name (e.g. 'Google')."},
    )
    login_url = fields.Str(
        metadata={"description": "URL to initiate login with this provider."},
    )


class OIDCConfigSchema(_Base):
    """OIDC configuration returned by the /oidc/ endpoint."""

    enabled = fields.Bool(
        metadata={"description": "Whether OIDC authentication is enabled."},
    )
    providers = fields.List(
        fields.Nested(OIDCProviderSchema),
        metadata={"description": "List of configured OIDC providers."},
    )
    disable_local_auth = fields.Bool(
        metadata={
            "description": "Whether local username/password authentication is disabled."
        },
    )
    auto_redirect = fields.Bool(
        metadata={
            "description": "Whether to auto-redirect when only one provider is configured."
        },
    )


class CredentialsSchema(_Base):
    """Login credentials (username + password)."""

    username = fields.Str(
        metadata={"description": "Username."},
    )
    password = fields.Str(
        metadata={"description": "Password."},
    )


class TransactionSchema(_Base):
    """A single object-level change within a committed transaction."""

    type = fields.Str(
        metadata={"description": "Action type: 'add', 'update', or 'delete'."},
    )
    _class = fields.Str(
        data_key="_class",
        metadata={"description": "Object class name (e.g. 'Person', 'Event')."},
    )
    handle = fields.Str(
        metadata={"description": "Handle of the affected object."},
    )
    old = fields.Raw(
        metadata={"description": "Object state before the change (null for adds)."},
    )
    new = fields.Raw(
        metadata={"description": "Object state after the change (null for deletes)."},
    )


class UndoTransactionSchema(_Base):
    """A committed database transaction as stored in the undo history."""

    id = fields.Int(
        metadata={"description": "Transaction ID."},
    )
    connection = fields.Raw(
        metadata={"description": "Internal connection object."},
    )
    first = fields.Int(
        metadata={"description": "ID of the first change in this transaction."},
    )
    last = fields.Int(
        metadata={"description": "ID of the last change in this transaction."},
    )
    undo = fields.Bool(
        metadata={"description": "Whether this transaction is from an undo action."},
    )
    timestamp = fields.Float(
        metadata={"description": "Unix timestamp when the transaction was committed."},
    )
    changes = fields.List(
        fields.Raw(),
        metadata={"description": "List of individual object changes."},
    )


class FilterRuleDescriptionSchema(_Base):
    """Description of a built-in Gramps filter rule."""

    category = fields.Str(
        metadata={"description": "Category of the filter rule."},
    )
    description = fields.Str(
        metadata={"description": "Long description of what the rule matches."},
    )
    labels = fields.List(
        fields.Str(),
        metadata={"description": "Labels for the rule's parameter fields."},
    )
    name = fields.Str(
        metadata={"description": "Display name of the rule."},
    )
    rule = fields.Str(
        metadata={"description": "Internal rule class name."},
    )


class FilterRuleSchema(_Base):
    """A filter rule instance (name + optional parameter values)."""

    name = fields.Str(
        metadata={"description": "Name of the filter rule class."},
    )
    regex = fields.Bool(
        metadata={
            "description": "Whether text values are treated as regular expressions."
        },
    )
    values = fields.List(
        fields.Raw(),
        metadata={"description": "Parameter values for the rule."},
    )


class CustomFilterSchema(_Base):
    """A user-defined custom filter with one or more rules."""

    comment = fields.Str(
        metadata={"description": "Comment describing the purpose of the filter."},
    )
    function = fields.Str(
        metadata={"description": "Logical operation: 'and', 'or', or 'one'."},
    )
    invert = fields.Bool(
        metadata={"description": "Whether the result set is inverted."},
    )
    name = fields.Str(
        metadata={"description": "Name of the custom filter."},
    )
    rules = fields.List(
        fields.Nested(FilterRuleSchema),
        metadata={"description": "Rules that make up this filter."},
    )


class NamespaceFiltersSchema(_Base):
    """All custom filters and available rule descriptions for one object namespace."""

    filters = fields.List(
        fields.Nested(CustomFilterSchema),
        metadata={"description": "Custom filters defined for this namespace."},
    )
    rules = fields.List(
        fields.Nested(FilterRuleDescriptionSchema),
        metadata={
            "description": "All available built-in filter rules for this namespace."
        },
    )


class LanguageSchema(_Base):
    """A language entry in the translations list."""

    current = fields.Str(
        metadata={"description": "Language name in the current locale."},
    )
    default = fields.Str(
        metadata={"description": "Language name in the default (English) locale."},
    )
    language = fields.Str(
        metadata={"description": "Language code (e.g. 'bg', 'de')."},
    )
    native = fields.Str(
        metadata={"description": "Language name in its own native locale."},
    )


class TranslationSchema(_Base):
    """A translated string pair."""

    original = fields.Str(
        metadata={"description": "The original (English) string."},
    )
    translation = fields.Str(
        metadata={"description": "The translated string."},
    )


class RelationshipSchema(_Base):
    """The relationship between two people."""

    relationship_string = fields.Str(
        metadata={"description": "Human-readable relationship description."},
    )
    distance_common_origin = fields.Int(
        metadata={
            "description": "Generations from person 1 to the common ancestor (-1 if none)."
        },
    )
    distance_common_other = fields.Int(
        metadata={
            "description": "Generations from person 2 to the common ancestor (-1 if none)."
        },
    )


class RelationshipItemSchema(_Base):
    """One entry in the list of all relationships between two people."""

    relationship_string = fields.Str(
        metadata={"description": "Human-readable relationship description."},
    )
    common_ancestors = fields.List(
        fields.Str(),
        metadata={"description": "Handles of common ancestors."},
    )


class ObjectCountsSchema(_Base):
    """Counts of primary object types in the database."""

    citations = fields.Float(metadata={"description": "Number of citations."})
    events = fields.Float(metadata={"description": "Number of events."})
    families = fields.Float(metadata={"description": "Number of families."})
    media = fields.Float(metadata={"description": "Number of media objects."})
    notes = fields.Float(metadata={"description": "Number of notes."})
    people = fields.Float(metadata={"description": "Number of people."})
    places = fields.Float(metadata={"description": "Number of places."})
    repositories = fields.Float(metadata={"description": "Number of repositories."})
    sources = fields.Float(metadata={"description": "Number of sources."})
    tags = fields.Float(metadata={"description": "Number of tags."})


class ResearcherSchema(_Base):
    """Information about the primary researcher of the genealogical data."""

    addr = fields.Str(metadata={"description": "Address."})
    city = fields.Str(metadata={"description": "City."})
    country = fields.Str(metadata={"description": "Country."})
    county = fields.Str(metadata={"description": "County."})
    email = fields.Str(metadata={"description": "Email address."})
    locality = fields.Str(metadata={"description": "Locality."})
    name = fields.Str(metadata={"description": "Name of the researcher."})
    phone = fields.Str(metadata={"description": "Phone number."})
    postal = fields.Str(metadata={"description": "Postal code."})
    state = fields.Str(metadata={"description": "State."})
    street = fields.Str(metadata={"description": "Street address."})


class MetadataSchema(_Base):
    """Server and database metadata returned by /api/metadata/."""

    database = fields.Dict(
        metadata={"description": "Information about the active database."},
    )
    default_person = fields.Str(
        metadata={"description": "Handle of the default person."},
    )
    gramps = fields.Dict(
        metadata={"description": "Information about the active Gramps installation."},
    )
    gramps_webapi = fields.Dict(
        metadata={"description": "Information about the Gramps Web API version."},
    )
    gramps_ql = fields.Dict(
        metadata={"description": "Information about the Gramps QL library."},
    )
    object_ql = fields.Dict(
        metadata={"description": "Information about the Object QL library."},
    )
    locale = fields.Dict(
        metadata={"description": "Information about the active locale."},
    )
    object_counts = fields.Nested(
        ObjectCountsSchema,
        metadata={"description": "Counts of primary object types."},
    )
    researcher = fields.Nested(
        ResearcherSchema,
        metadata={"description": "Information about the primary researcher."},
    )
    search = fields.Dict(
        metadata={"description": "Information about search-related libraries."},
    )
    server = fields.Dict(
        metadata={"description": "Information about server capabilities."},
    )
    surnames = fields.List(
        fields.Str(),
        metadata={
            "description": "All surnames found in the database (when requested)."
        },
    )


class BookmarksSchema(_Base):
    """All bookmarks for the current user, grouped by object type."""

    class Meta:
        unknown = INCLUDE

    # Keys are object-type strings (e.g. "people", "families"); values are handle lists.


class DefaultTypesSchema(_Base):
    """Default type lists for each Gramps type category."""

    class Meta:
        unknown = INCLUDE


class DefaultTypeMapSchema(_Base):
    """Mapping from integer type code to string name for a type category."""

    class Meta:
        unknown = INCLUDE


class CustomTypesSchema(_Base):
    """User-defined custom type lists for each Gramps type category."""

    class Meta:
        unknown = INCLUDE


class TypesSchema(_Base):
    """All Gramps types, both default and custom."""

    custom = fields.Nested(
        CustomTypesSchema,
        metadata={"description": "User-defined custom types."},
    )
    default = fields.Nested(
        DefaultTypesSchema,
        metadata={"description": "Built-in default types."},
    )


class NameFormatSchema(_Base):
    """A name display format definition."""

    active = fields.Bool(
        metadata={"description": "Whether this format is currently in use."},
    )
    format = fields.Str(
        metadata={"description": "The format string."},
    )
    name = fields.Str(
        metadata={"description": "Display name of the format."},
    )
    number = fields.Int(
        metadata={"description": "Numeric identifier for the format."},
    )


class NameGroupMappingSchema(_Base):
    """A mapping from one surname spelling to its canonical group."""

    surname = fields.Str(
        metadata={"description": "The surname to be grouped."},
    )
    group = fields.Str(
        metadata={
            "description": "The canonical surname this spelling is grouped with."
        },
    )


class SpanSchema(_Base):
    """An elapsed-time span."""

    span = fields.Str(
        metadata={"description": "Human-readable description of the elapsed time."},
    )


class ExporterSchema(_Base):
    """Description of an available data exporter plugin."""

    description = fields.Str(
        metadata={"description": "Description of the export format and its use."},
    )
    extension = fields.Str(
        metadata={"description": "Default file extension for this format."},
    )
    module = fields.Str(
        metadata={"description": "Plugin module name."},
    )


class ImporterSchema(_Base):
    """Description of an available data importer plugin."""

    description = fields.Str(
        metadata={"description": "Description of the import format and its use."},
    )
    extension = fields.Str(
        metadata={"description": "File extension this importer handles."},
    )
    module = fields.Str(
        metadata={"description": "Plugin module name."},
    )


class ReportHelpOptionSchema(_Base):
    """Help information for a single report option (heterogeneous array)."""

    class Meta:
        unknown = INCLUDE


class ReportSchema(_Base):
    """Description of an available Gramps report plugin."""

    authors = fields.List(
        fields.Str(),
        metadata={"description": "Report author names."},
    )
    authors_email = fields.List(
        fields.Str(),
        metadata={"description": "Email addresses of report authors."},
    )
    category = fields.Int(
        metadata={"description": "Report category code."},
    )
    description = fields.Str(
        metadata={"description": "Description of the report."},
    )
    id = fields.Str(
        metadata={"description": "Report identifier."},
    )
    name = fields.Str(
        metadata={"description": "Display name of the report."},
    )
    options_dict = fields.Dict(
        metadata={"description": "All report options with their default values."},
    )
    options_help = fields.Dict(
        metadata={"description": "Help information for all report options."},
    )
    report_modes = fields.List(
        fields.Int(),
        metadata={"description": "Supported report output modes."},
    )
    version = fields.Str(
        metadata={"description": "Version of the report plugin."},
    )


class SearchResultSchema(_Base):
    """A single result from a full-text or semantic search."""

    handle = fields.Str(
        metadata={"description": "Handle of the matching object."},
    )
    object = fields.Raw(
        metadata={"description": "The matching object data."},
    )
    object_type = fields.Str(
        metadata={"description": "Type of the matching object (e.g. 'person')."},
    )
    score = fields.Float(
        metadata={"description": "Relevance score."},
    )


class ChatResponseSchema(_Base):
    """Response from the AI chat endpoint."""

    response = fields.Str(
        metadata={"description": "The assistant's answer."},
    )
    metadata = fields.Dict(
        metadata={
            "description": "Optional execution metadata (included when verbose=true)."
        },
    )


class LivingSchema(_Base):
    """Whether a person is estimated to be currently alive."""

    living = fields.Bool(
        metadata={"description": "True if the person is estimated to be alive."},
    )


class LivingDatesSchema(_Base):
    """Estimated birth and death dates for a person."""

    birth = fields.Str(
        metadata={"description": "Estimated birth date."},
    )
    death = fields.Str(
        metadata={"description": "Estimated death date."},
    )
    explain = fields.Str(
        metadata={"description": "Explanation of how the dates were determined."},
    )
    other = fields.Nested(
        PersonSchema,
        metadata={"description": "Related person record used in the estimation."},
    )


class TimelinePersonProfileSchema(_Base):
    """Profile of a person as they appear on a timeline."""

    age = fields.Str(
        metadata={"description": "Age of the person at the time of the event."},
    )
    birth = fields.Nested(
        EventProfileSchema,
        metadata={"description": "Birth event profile."},
    )
    death = fields.Nested(
        EventProfileSchema,
        metadata={"description": "Death event profile."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the person."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the person."},
    )
    name_display = fields.Str(
        metadata={"description": "Full display name."},
    )
    name_given = fields.Str(
        metadata={"description": "Given (first) name."},
    )
    name_surname = fields.Str(
        metadata={"description": "Surname."},
    )
    name_suffix = fields.Str(
        metadata={"description": "Name suffix."},
    )
    relationship = fields.Str(
        metadata={"description": "Relationship to the anchor person."},
    )
    sex = fields.Str(
        metadata={"description": "Sex identifier ('M', 'F', or 'U')."},
    )


class TimelineEventProfileSchema(_Base):
    """A single event entry in a person or family timeline response."""

    age = fields.Str(
        metadata={"description": "Age of the anchor person at the time of the event."},
    )
    citations = fields.Int(
        metadata={"description": "Total number of supporting citations."},
    )
    confidence = fields.Int(
        metadata={"description": "Highest confidence rating among citations."},
    )
    date = fields.Str(
        metadata={"description": "Date of the event as a formatted string."},
    )
    description = fields.Str(
        metadata={"description": "Description of the event."},
    )
    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier for the event."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the event."},
    )
    label = fields.Str(
        metadata={
            "description": "Generated label accounting for the relationship (e.g. 'Birth of Stepsister')."
        },
    )
    media = fields.List(
        fields.Str(),
        metadata={"description": "Handles of media items for this event."},
    )
    person = fields.Nested(
        TimelinePersonProfileSchema,
        metadata={"description": "Profile of the person associated with this event."},
    )
    place = fields.Nested(
        PlaceProfileSchema,
        metadata={"description": "Profile of the place where the event occurred."},
    )
    type = fields.Str(
        metadata={"description": "Type of the event."},
    )


class DnaSegmentSchema(_Base):
    """A single matching chromosome segment from a DNA comparison."""

    chromosome = fields.Str(
        metadata={"description": "Chromosome identifier."},
    )
    start = fields.Int(
        metadata={"description": "Start position of the segment."},
    )
    stop = fields.Int(
        metadata={"description": "End position of the segment."},
    )
    side = fields.Str(
        metadata={
            "description": "Side: 'M' (maternal), 'P' (paternal), or 'U' (unknown)."
        },
    )
    cM = fields.Float(
        metadata={"description": "Genetic distance in centiMorgans."},
    )
    SNPs = fields.Int(
        metadata={"description": "Number of matching SNPs."},
    )
    comment = fields.Str(
        metadata={"description": "Optional comment about the segment."},
    )


class DnaMatchSchema(_Base):
    """DNA match information between two people."""

    handle = fields.Str(
        metadata={"description": "Handle of the matching person."},
    )
    relation = fields.Str(
        metadata={"description": "Estimated relationship to the matching person."},
    )
    ancestor_handles = fields.List(
        fields.Str(),
        metadata={"description": "Handles of latest common ancestors."},
    )
    ancestor_profiles = fields.List(
        fields.List(fields.Nested(PersonProfileSchema)),
        metadata={"description": "Profiles of latest common ancestors."},
    )
    segments = fields.List(
        fields.Nested(DnaSegmentSchema),
        metadata={"description": "Details of each matching chromosome segment."},
    )
    person_ref_idx = fields.Int(
        metadata={
            "description": "Index into the person's person_ref_list for this match."
        },
    )
    note_handles = fields.List(
        fields.Str(),
        metadata={
            "description": "Handles of notes associated with the match's segments."
        },
    )
    raw_data = fields.List(
        fields.Str(),
        metadata={"description": "Raw note strings containing segment data."},
    )


class CladeAgeInfoSchema(_Base):
    """Age estimation data for a haplogroup clade."""

    formed = fields.Float(
        allow_none=True,
        metadata={"description": "Estimated years ago the clade was formed."},
    )
    formed_confidence_interval = fields.List(
        fields.Float(),
        allow_none=True,
        metadata={
            "description": "95% confidence interval [lower, upper] for the formed age."
        },
    )
    most_recent_common_ancestor = fields.Float(
        allow_none=True,
        metadata={
            "description": "Estimated years ago the most recent common ancestor was born."
        },
    )
    most_recent_common_ancestor_confidence_interval = fields.List(
        fields.Float(),
        allow_none=True,
        metadata={
            "description": "95% confidence interval for the most recent common ancestor age."
        },
    )


class CladeInfoSchema(_Base):
    """Information about a Y-DNA haplogroup clade."""

    name = fields.Str(
        metadata={"description": "Clade ID (e.g. 'BY61636')."},
    )
    age_info = fields.Nested(
        CladeAgeInfoSchema,
        allow_none=True,
        metadata={"description": "Age information for the clade."},
    )
    score = fields.Float(
        allow_none=True,
        metadata={"description": "Match score for this clade."},
    )


class YDnaResponseSchema(_Base):
    """Y-DNA analysis result for a person.

    All fields are optional; an empty object ``{}`` is returned when no Y-DNA
    attribute is found on the person.
    """

    clade_lineage = fields.List(
        fields.Nested(CladeInfoSchema),
        metadata={
            "description": "Ordered list of Y-DNA haplogroup clade assignments, "
            "from broadest to most specific."
        },
    )
    tree_version = fields.Str(
        metadata={
            "description": "Version of the YFull tree used for clade assignment."
        },
    )
    raw_data = fields.Str(
        metadata={
            "description": "Raw Y-DNA SNP data string. Only present if raw=true was requested."
        },
    )


class RecordFactObjectSchema(_Base):
    """A single object referenced by a genealogical fact."""

    gramps_id = fields.Str(
        metadata={"description": "Alternate user-managed identifier."},
    )
    handle = fields.Str(
        metadata={"description": "Unique handle for the object."},
    )
    name = fields.Str(
        metadata={"description": "Description of the object."},
    )
    object = fields.Str(
        metadata={"description": "Object type (e.g. 'Person')."},
    )
    value = fields.Str(
        metadata={"description": "Value supporting the fact."},
    )


class RecordFactSchema(_Base):
    """A single genealogical record fact (statistic or record)."""

    description = fields.Str(
        metadata={"description": "Human-readable description of the fact."},
    )
    key = fields.Str(
        metadata={"description": "Unique identifier for the fact type."},
    )
    objects = fields.List(
        fields.Nested(RecordFactObjectSchema),
        metadata={"description": "Objects the fact is about."},
    )


class TaskReferenceSchema(_Base):
    """Reference to a background task."""

    href = fields.Str(
        metadata={"description": "URL of the task status endpoint."},
    )
    id = fields.Str(
        metadata={"description": "Unique identifier of the task."},
    )


class TreeSchema(_Base):
    """A family tree (database) on the server."""

    name = fields.Str(
        metadata={"description": "Human-readable name of the tree."},
    )
    id = fields.Str(
        metadata={"description": "Unique identifier of the tree."},
    )
    quota_media = fields.Int(
        allow_none=True,
        metadata={"description": "Maximum total size in bytes for media objects."},
    )
    quota_people = fields.Int(
        allow_none=True,
        metadata={"description": "Maximum number of people allowed in the tree."},
    )
    usage_media = fields.Int(
        metadata={"description": "Current total size of media objects in bytes."},
    )
    usage_people = fields.Int(
        metadata={"description": "Current number of people in the tree."},
    )
    enabled = fields.Bool(
        metadata={"description": "Whether the tree is enabled."},
    )
    min_role_ai = fields.Int(
        allow_none=True,
        metadata={
            "description": "Minimum user role required to use the AI chat endpoint."
        },
    )
