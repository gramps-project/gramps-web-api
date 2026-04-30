# Gramps Web API

This is the repository for **Gramps Web API**, a Python REST API for [Gramps](https://gramps-project.org).

It allows to query and manipulate a [Gramps](https://gramps-project.org) family tree database via the web.

Gramps Web API is the backend of [Gramps Web](https://www.grampsweb.org/), a genealogy web app based on Gramps, but can also be used as backend for other tools.

## More information

- API documentation for Gramps Web API: https://gramps-project.github.io/gramps-web-api/
- Developer documentation for Gramps Web API: https://www.grampsweb.org/development/backend/
- Documentation for Gramps Web: https://www.grampsweb.org

## Trusted JWT / IAP authentication

Gramps Web API can authenticate users from an identity-aware proxy (IAP) that
forwards a signed JWT assertion. This is the pattern used by Pomerium,
Cloudflare Access, Google Cloud IAP, and similar tools.

The application verifies the JWT signature, issuer, audience, and expiry before
creating a normal Gramps Web session. Unsigned convenience headers such as
forwarded email, name, or group headers are not trusted for login.

### Minimal configuration

Enable Trusted JWT authentication and configure the header, JWKS URL, issuer,
and audience for your proxy:

```bash
GRAMPSWEB_TRUSTED_JWT_ENABLED=true
GRAMPSWEB_TRUSTED_JWT_PROVIDER_ID=pomerium
GRAMPSWEB_TRUSTED_JWT_HEADER=X-Pomerium-Jwt-Assertion
GRAMPSWEB_TRUSTED_JWT_JWKS_URL=https://gramps.example.com/.well-known/pomerium/jwks.json
GRAMPSWEB_TRUSTED_JWT_ISSUER=gramps.example.com
GRAMPSWEB_TRUSTED_JWT_AUDIENCE=gramps.example.com
GRAMPSWEB_TRUSTED_JWT_ALGORITHMS=ES256
```

`TRUSTED_JWT_PROVIDER_ID` becomes part of the account association key stored in
the Gramps Web user database. Configure a stable value for each proxy/issuer
(`pomerium`, `cloudflare-access`, `google-iap`, etc.) so existing account links
do not collide if you change IAP providers later.

For Pomerium, confirm which issuer format your route uses. The default assertion
issuer is the route host (`gramps.example.com`); if `jwt_issuer_format = "uri"`
is configured, use the full URI issuer (`https://gramps.example.com/`).

### Provider examples

| Provider | Header | JWKS URL | Issuer | Audience |
|---|---|---|---|---|
| Pomerium | `X-Pomerium-Jwt-Assertion` | `https://<route-host>/.well-known/pomerium/jwks.json` | `<route-host>` by default; `https://<route-host>/` when Pomerium `jwt_issuer_format` is `uri` | `<route-host>` |
| Cloudflare Access | `Cf-Access-Jwt-Assertion` | `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs` | `https://<team-name>.cloudflareaccess.com` | The Access application AUD tag |
| Google Cloud IAP | `X-Goog-IAP-JWT-Assertion` | `https://www.gstatic.com/iap/verify/public_key-jwk` | `https://cloud.google.com/iap` | `/projects/<project-number>/apps/<project-id>` or `/projects/<project-number>/global/backendServices/<backend-service-id>` |

### Roles and provisioning

By default, new users created through Trusted JWT login are disabled. Choose one
of these models:

```bash
# Single-user app behind a strict IAP policy.
GRAMPSWEB_TRUSTED_JWT_DEFAULT_ROLE=owner

# Multi-user app: keep unknown users disabled and map proxy groups to roles.
GRAMPSWEB_TRUSTED_JWT_DEFAULT_ROLE=disabled
GRAMPSWEB_TRUSTED_JWT_ROLE_CLAIM=groups
GRAMPSWEB_TRUSTED_JWT_GROUP_OWNER=family-tree-owners
GRAMPSWEB_TRUSTED_JWT_GROUP_EDITOR=family-tree-editors
GRAMPSWEB_TRUSTED_JWT_GROUP_MEMBER=family-tree-members
```

For an additional local guardrail, set an email allowlist:

```bash
GRAMPSWEB_TRUSTED_JWT_ALLOWED_EMAILS=you@example.com,partner@example.com
```

### Security notes

- The JWKS URL must use HTTPS by default. For local development only, set
  `GRAMPSWEB_TRUSTED_JWT_REQUIRE_HTTPS_JWKS=false`.
- Only asymmetric JWT algorithms are accepted (`RS*` and `ES*`). Unsigned tokens
  and symmetric `HS*` tokens are rejected.
- `exp`, `iss`, and `aud` are required. Configure issuer and audience
  explicitly; do not rely on trust-on-first-use behavior.
- Keep local password login enabled while validating a new IAP setup. Once the
  Trusted JWT login flow is confirmed, disable local password login so an IAP
  account cannot be bypassed or taken over through Gramps Web's password forms.
  This also disables local password change and reset endpoints for external-auth
  deployments:

```bash
GRAMPSWEB_OIDC_DISABLE_LOCAL_AUTH=true
```

Optional settings include provider display name, accepted asymmetric algorithms,
JWT leeway, claim names, allowed email allowlist, default role, group-to-role
mapping, and logout URL.

## Related projects

- Gramps Web frontend repository: https://github.com/gramps-project/gramps-web
