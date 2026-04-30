# Gramps Web API

This is the repository for **Gramps Web API**, a Python REST API for [Gramps](https://gramps-project.org).

It allows to query and manipulate a [Gramps](https://gramps-project.org) family tree database via the web.

Gramps Web API is the backend of [Gramps Web](https://www.grampsweb.org/), a genealogy web app based on Gramps, but can also be used as backend for other tools.

## More information

- API documentation for Gramps Web API: https://gramps-project.github.io/gramps-web-api/
- Developer documentation for Gramps Web API: https://www.grampsweb.org/development/backend/
- Documentation for Gramps Web: https://www.grampsweb.org

## Trusted JWT / IAP authentication

Gramps Web API can authenticate users from a trusted, identity-aware proxy that
forwards a signed JWT assertion. This is the pattern used by Pomerium,
Cloudflare Access, Google Cloud IAP, and similar tools. The application verifies
the JWT signature and configured claims before creating a normal Gramps Web
session; unsigned convenience headers such as forwarded email or name headers
are not trusted for login.

At minimum, enable Trusted JWT authentication and configure the JWT header, JWKS
URL, issuer, and audience:

```bash
GRAMPSWEB_TRUSTED_JWT_ENABLED=true
GRAMPSWEB_TRUSTED_JWT_PROVIDER_ID=pomerium
GRAMPSWEB_TRUSTED_JWT_HEADER=X-Pomerium-Jwt-Assertion
GRAMPSWEB_TRUSTED_JWT_JWKS_URL=https://gramps.example.com/.well-known/pomerium/jwks.json
GRAMPSWEB_TRUSTED_JWT_ISSUER=https://auth.example.com
GRAMPSWEB_TRUSTED_JWT_AUDIENCE=https://gramps.example.com
```

The JWKS URL must use HTTPS by default. Configure a stable
`TRUSTED_JWT_PROVIDER_ID` for each proxy/issuer so existing account links do not
collide if you change IAP providers later.

Optional settings include provider display name, accepted asymmetric algorithms
(`RS*`/`ES*`; unsigned and `HS*` tokens are rejected), JWT leeway, claim names,
allowed email allowlist, default role, group-to-role mapping, and logout URL.

## Related projects

- Gramps Web frontend repository: https://github.com/gramps-project/gramps-web
