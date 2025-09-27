# Gramps Web API

This is the repository for **Gramps Web API**, a Python REST API for [Gramps](https://gramps-project.org).

It allows to query and manipulate a [Gramps](https://gramps-project.org) family tree database via the web.

Gramps Web API is the backend of [Gramps Web](https://www.grampsweb.org/), a genealogy web app based on Gramps, but can also be used as backend for other tools.

## More information

- API documentation for Gramps Web API: https://gramps-project.github.io/gramps-web-api/
- Developer documentation for Gramps Web API: https://www.grampsweb.org/dev-backend/
- Documentation for Gramps Web: https://www.grampsweb.org

## OIDC Configuration

Gramps Web API supports OpenID Connect (OIDC) authentication with multiple providers. You can configure built-in providers (Google, Microsoft, GitHub) or use a custom OIDC provider.

### Custom OIDC Provider

To configure a custom OIDC provider, set these environment variables:

- `GRAMPSWEB_OIDC_ENABLED=true` - Enable OIDC authentication
- `GRAMPSWEB_OIDC_ISSUER` - OIDC provider issuer URL
- `GRAMPSWEB_OIDC_CLIENT_ID` - OAuth client ID
- `GRAMPSWEB_OIDC_CLIENT_SECRET` - OAuth client secret
- `GRAMPSWEB_OIDC_NAME` - Custom display name for the provider (defaults to "OIDC")
- `GRAMPSWEB_OIDC_REDIRECT_URI` - Redirect URI for OAuth flow
- `GRAMPSWEB_OIDC_SCOPES` - OAuth scopes (defaults to "openid email profile")
- `GRAMPSWEB_OIDC_DISABLE_LOCAL_AUTH=true` - Disable local username/password authentication
- `GRAMPSWEB_OIDC_AUTO_REDIRECT=true` - Automatically redirect to OIDC when only one provider is configured

### Built-in Providers

For built-in providers, use these patterns:

- `GRAMPSWEB_OIDC_GOOGLE_CLIENT_ID` and `GRAMPSWEB_OIDC_GOOGLE_CLIENT_SECRET`
- `GRAMPSWEB_OIDC_MICROSOFT_CLIENT_ID` and `GRAMPSWEB_OIDC_MICROSOFT_CLIENT_SECRET`
- `GRAMPSWEB_OIDC_GITHUB_CLIENT_ID` and `GRAMPSWEB_OIDC_GITHUB_CLIENT_SECRET`

## Related projects

- Gramps Web frontend repository: https://github.com/gramps-project/gramps-web
