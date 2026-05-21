# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with Gramps Web API.

## Reporting a Problem

When requesting support, please include the following information so the team can help you effectively:

### Before opening an issue

- **When did the error occur?** Was it during initial setup, or after the application was running normally?
- **What were you trying to do?** (e.g., register a new user, import a GEDCOM file, browse a family tree)
- **What did you try?** Any workaround steps you already attempted

### Collecting information to share

**Screenshots:**
If the error appears in the web interface, take a screenshot showing the full error message or the page where the problem occurred.

**Logs:**
Docker logs contain detailed information about API errors. Retrieve logs with:

```bash
# Get logs from the container
docker compose logs

# Or from a specific service
docker compose logs grampswebapi

# For the last 100 lines
docker compose logs --tail=100
```

**Browser console:**
For errors in the web interface, open the browser developer tools (F12) and check the Console tab for error messages.

**API response:**
If the error occurs when calling the API directly, include the full HTTP response including the status code and response body.

---

## Error Code Reference

### HTTP 503 — Tree Temporarily Disabled

**What it means:** The family tree you are trying to access has been temporarily disabled by an administrator.

**Common causes:**
- The tree owner has paused access while performing maintenance
- The tree's database file is being updated or synchronized
- A configuration issue has disabled the tree

**What to do:**
1. Wait a few minutes and try again
2. Contact the tree owner or server administrator to confirm whether the tree is intentionally disabled
3. If you are the administrator, check the server logs for details: `docker compose logs grampswebapi | grep -i disabled`

---

### HTTP 405 — Not Allowed

A `405 Method Not Allowed` response indicates that the action you attempted is not permitted in the current context. The specific reason depends on the endpoint:

#### Registration not allowed

**Cause:** User registration is disabled on this server.

**What to do:**
- Contact the server administrator to enable registration, or
- Use an existing account if you already have one

#### Users already exist

**Cause:** Attempted to create a new user, but the server has reached its maximum number of allowed users (single-tree setup).

**What to do:**
- Use an existing user account, or
- Contact the administrator about upgrading to a multi-tree setup

#### OIDC authentication not enabled

**Cause:** Your server does not have OpenID Connect (OIDC) authentication configured.

**What to do:**
- Log in with the standard username/password method, or
- Ask your administrator to enable OIDC authentication

#### Not allowed in single-tree setup

**Cause:** You attempted an action that is only available when running multiple family trees.

**What to do:**
- Some features require a multi-tree server configuration
- Contact your administrator if you need multi-tree support

---

## Getting Further Help

If your issue is not covered here:

1. Check the [Gramps Web API documentation](https://gramps-project.github.io/gramps-webapi/)
2. Search existing issues in the [issue tracker](https://github.com/gramps-project/gramps-web-api/issues)
3. Start a new issue with the information described above under "Reporting a Problem"