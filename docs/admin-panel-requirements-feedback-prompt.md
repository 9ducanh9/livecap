Update the Admin Panel requirements document with the following changes, based on
implementation experience from the existing v1 admin overview endpoint
(`GET /api/admin/overview`, commit `8dc7167`) and a real login incident during
testing today:

1. **Add an audit logging requirement** (new Requirement, after Requirement 6 -
   Change Tier). Every mutating admin action (disable user, enable user, reset
   password, change tier) must write an audit record containing: admin user id,
   target user id, action type, previous value (where applicable), new value,
   and timestamp. Acceptance criteria: "WHEN an Admin_User performs a disable,
   enable, reset-password, or tier-change action, THE Admin_API SHALL persist
   an audit record before returning success." Add an Audit_Log_Entry term to
   the Glossary.

2. **Requirement 3 (Search) and Requirement 4/5 (Disable/Enable/Reset
   Password) must account for Cognito Username vs. email mismatch.** This
   user pool has `username_attributes = ["email"]`, but a user who signs in
   via the Google identity provider gets a Cognito `Username` like
   `Google_<sub>`, distinct from a native email/password account -- the two
   can share the same email attribute but are separate Cognito user records
   with separate Usernames. Confirmed today: attempting email/password sign-in
   for an account that was actually created via Google returned
   `NotAuthorizedException` (wrong password), not "user not found," which is
   the exact failure mode this ambiguity produces.
   - Add to Requirement 3: "IF a search by email matches more than one Cognito
     user record (e.g., a native and a federated identity sharing the same
     email attribute), THEN THE Admin_API SHALL return all matching
     User_Records distinguished by their Cognito Username, and THE
     User_Management_Page SHALL display the identity provider for each row."
   - Add to Requirement 5 (Reset Password): "IF the target user's Cognito
     account has no native password (federated-only, e.g., Google), THEN THE
     Admin_API SHALL return an error indicating password reset is not
     applicable, and THE User_Management_Page SHALL disable the reset-password
     action for that user rather than allow the request."
   - Clarify in Requirement 4/5 acceptance criteria that all Cognito Admin*
     calls (AdminDisableUser, AdminEnableUser, AdminResetUserPassword) must
     target the user by Cognito Username (or sub), never by email.

3. **Requirement 6 (Change Tier) needs a Stripe-consistency note.** Add
   acceptance criterion: "IF the target user has an active Stripe
   subscription and an admin manually changes their tier, THEN THE Admin_API
   SHALL include a warning in the response noting that the change does not
   modify the underlying Stripe subscription, and THE User_Management_Page
   SHALL surface this warning to the admin before confirming the action."

4. **Requirement 9/10 (Usage Analytics) needs a data-retention constraint.**
   The `usage_quota` DynamoDB table has a 90-day TTL on monthly usage items.
   Add acceptance criterion: "THE Usage_Analytics_Page SHALL NOT display or
   request trend data older than 90 days, and SHALL indicate that historical
   data beyond this window is unavailable."

5. **Requirement 11 (MRR) needs an explicit source-of-truth decision.**
   Current wording ("summing the monthly price of each active paid
   subscription") is ambiguous about whether the count comes from the
   internal DynamoDB tier field or live Stripe subscription data. Recommend
   rewriting to source MRR from the Stripe Subscriptions API directly (more
   accurate under coupons/discounts/proration) rather than deriving it from
   internal tier counts, and note the trade-off (one extra external API call
   per page load) explicitly in the requirement.

6. **Requirement 12 (System Health / Cost) needs two clarifications.** Add:
   "THE cost estimate SHALL be labeled with its data timestamp (AWS Cost
   Explorer data typically lags ~24 hours) so it is not mistaken for a
   real-time figure," and "THE Admin_API SHALL call the Cost Explorer API in
   `us-east-1` regardless of the primary deployment region, per AWS's
   requirement that Cost Explorer is only accessible via that region."

7. **Add a phased-delivery note to the Introduction**, since this expands
   substantially on the existing read-only v1 endpoint: suggest splitting
   delivery into Phase 1 (pagination/search/filter on the existing overview),
   Phase 2 (mutating user actions: disable/enable/reset/tier + audit log),
   Phase 3 (usage analytics), Phase 4 (revenue + system health), so each
   phase's Terraform IAM changes can be reviewed and applied independently
   rather than as one large plan.
