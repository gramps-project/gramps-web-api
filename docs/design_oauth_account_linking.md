# Design Document: OAuth Account Linking for Gramps Web API

## Current State

Gramps Web API supports two independent authentication methods:

1. **Password-based accounts**: Traditional username/password authentication via `/api/token/`
2. **OAuth/OIDC accounts**: Social login via providers (Google, Microsoft, GitHub, or custom OIDC)

These are currently **mutually exclusive**:
- Password users cannot add OAuth providers to their accounts
- OAuth users cannot add password-based login to their accounts
- The `OIDCAccount` table exists and supports multiple OAuth provider associations per user, but no API exists to initiate linking

**Relevant existing infrastructure:**
- `OIDCAccount` model in `gramps_webapi/auth/__init__.py` (lines 483-507)
- `create_oidc_account()` function to create associations
- `get_user_oidc_accounts()` function to list linked providers
- `get_oidc_account()` function to look up user by provider+subject

## Feature Overview

Allow users to link their existing account to one or more OAuth providers. After linking, users can authenticate using either their password OR any linked OAuth provider.

## Design Decisions

### Security Considerations

1. **Password verification required**: Before linking a new OAuth provider, the user must verify their password to prevent account takeover if session is hijacked.

2. **Email verification (optional)**: Consider requiring email verification if the OAuth provider's email matches the account's email. This prevents linking accounts with email mismatch.

3. **Conflict prevention**: A new OAuth account (provider+subject) can only be linked if it isn't already associated with another user.

4. **OAuth provider scope**: Only link providers that are configured and enabled (validated via `get_available_oidc_providers()`).

### User Experience Flow

```
User Flow for Linking OAuth Provider:
1. User logs in with password
2. User navigates to account settings (frontend)
3. User clicks "Link OAuth Provider" and selects provider
4. Frontend initiates OAuth flow with new state parameter: action=link
5. OAuth callback detects action=link, verifies password in session/state
6. System creates OIDCAccount association for current user
7. User redirected to success page
8. User can now login with either password or OAuth provider
```

## API Specification

### New Endpoint: POST `/api/oidc/link/`

Initiates the OAuth flow with intent to link to authenticated account.

**Query Parameters:**
- `provider` (required): OAuth provider ID (e.g., `google`, `microsoft`, `github`, `custom`)
- `password` (required): User's current password (for verification)

**Response:** Redirect to OAuth provider authorization URL

**Error Responses:**
- `400 Bad Request`: Invalid provider or missing password
- `401 Unauthorized`: Invalid password
- `403 Forbidden`: Provider not configured

### Modified Endpoint: GET `/api/oidc/callback/<provider_id>`

After OAuth callback, if `action=link` in state:
1. Verify the user is already authenticated via JWT
2. Verify password hash matches the state payload
3. Check no conflict (provider+subject not already linked)
4. Create OIDCAccount for the authenticated user
5. Return success page or redirect with success message

### New Endpoint: DELETE `/api/oidc/accounts/<provider_id>/`

Unlink an OAuth provider from the current account.

**Permissions:** `PERM_EDIT_OWN_USER` (user can unlink their own providers)

**Response:** `204 No Content` on success

**Constraints:**
- Cannot unlink if it is the only authentication method
- Cannot unlink last provider if OIDC is the only auth method and password auth is disabled

### New Endpoint: GET `/api/users/-/oidc-accounts/`

List all OAuth accounts linked to the current user.

**Response:**
```json
{
  "oidc_accounts": [
    {
      "provider_id": "google",
      "email": "user@example.com",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "account_source": "Custom OIDC"
}
```

## Database Changes

No schema changes required. The existing `OIDCAccount` table already supports:
- Multiple OAuth accounts per user
- Cascading delete when user is deleted
- Unique constraint on (provider_id, subject_id)

## Implementation Checklist

### Backend Changes

- [x] Add `link_oidc_account()` function in `gramps_webapi/auth/__init__.py`
- [x] Add `delete_oidc_account()` function in `gramps_webapi/auth/__init__.py`
- [x] Create `OIDCLinkResource` class in `gramps_webapi/api/resources/oidc.py`
- [x] Create `OIDCLinkCallbackResource` class in `gramps_webapi/api/resources/oidc.py`
- [x] Create `OIDCUnlinkResource` class in `gramps_webapi/api/resources/oidc.py`
- [x] Create `OIDCAccountsListResource` class in `gramps_webapi/api/resources/oidc.py`
- [x] Add schemas for request/response validation
- [x] Register new endpoints in `gramps_webapi/api/__init__.py`
- [x] Add appropriate rate limiting
- [x] Add tests for new functionality in `tests/test_endpoints/test_oidc_link.py`

### Security Requirements

- [x] Password verification before linking
- [x] Conflict detection (prevent duplicate provider+subject)
- [x] CSRF protection via state parameter
- [ ] Audit logging for account linking events (deferred)

### Frontend Requirements (external)

- [ ] Account settings page with OAuth linking options
- [ ] Provider selection UI
- [ ] Unlink confirmation dialog
- [ ] Success/error notifications

## Example State Parameter for OAuth

```json
{
  "action": "link",
  "user_id": "<user_guid>",
  "password_hash": "<hash_of_current_password>",
  "redirect_uri": "<frontend_callback_url>"
}
```

This ensures:
1. Only the authenticated user can complete the link
2. Password verification is required (hash included in state)
3. CSRF protection via state token

## Migration Path

This feature is additive and doesn't require migrations. Existing users can optionally link OAuth providers; behavior is opt-in.

## Testing Scenarios

1. **Happy path**: Password user links Google account, then logs in with Google
2. **Conflict**: Try to link Google account that's already linked to another user → error
3. **Invalid password**: Wrong password in link request → 401
4. **Unlink last provider**: Error when trying to unlink only auth method
5. **Multiple links**: User links Google and GitHub, can login with either
6. **Role preservation**: Linked OAuth users maintain their original role

## Related Configuration

No new configuration required. Uses existing `OIDC_*` environment variables for provider configuration.

## Alternative Approaches Considered

### 1. Email-based automatic linking (rejected)
Automatically merge accounts if OAuth email matches existing password account.
- **Rejected**: "Email linking removed for security" (per existing code comment)
- Risk: Email spoofing, unverified emails

### 2. Admin-initiated linking (out of scope)
Admin can link accounts on behalf of users.
- Could be added as future enhancement
- Would require additional permission: `PERM_LINK_USERS`

### 3. Token-based linking
Use a time-limited token emailed to user for verification before linking.
- More secure but adds friction
- Could be added as optional enhancement for sensitive scenarios