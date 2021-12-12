# Gramps Web API

Gramps Web API is a web application that provides a RESTful API to a [Gramps](https://gramps-project.org/) family tree database.

The API can be used as a backend for web or mobile applications that allow collaborative editing of a Gramps database.

## Main features

- Query all Gramps objects: people, families, places, events, repositories, sources, citations, media objects, notes, tags
- Add new objects and edit existing ones
- Full-text search engine
- Media file thumbnails
- Multi-user authentication system based on JSON web tokens
- Generate and download Gramps reports
- Use and create Gramps filters
- Export the family tree as Gramps XML or GEDCOM

As Python application, being powered by the `gramps` library itself (which powers also the Desktop application), Gramps Web API does not reinvent the wheel but builds on a strong foundation.
