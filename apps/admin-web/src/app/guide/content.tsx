import type { ReactNode } from "react";

export type GuideModule = "platform" | "talent-flow" | "birthday" | "spark";

export type GuideSection = {
  id: string;
  title: string;
  module: GuideModule;
  body: ReactNode;
};

const P = ({ children }: { children: ReactNode }) => <p className="text-sm leading-relaxed text-dt-text-secondary">{children}</p>;
const Quote = ({ children }: { children: ReactNode }) => (
  <blockquote className="rounded-lg border-l-4 border-dt-orange bg-dt-surface-warm px-4 py-3 text-sm italic text-dt-text-primary">
    {children}
  </blockquote>
);
const Ol = ({ children }: { children: ReactNode }) => (
  <ol className="list-decimal space-y-1.5 pl-5 text-sm text-dt-text-secondary">{children}</ol>
);
const Ul = ({ children }: { children: ReactNode }) => (
  <ul className="list-disc space-y-1.5 pl-5 text-sm text-dt-text-secondary">{children}</ul>
);
const Code = ({ children }: { children: ReactNode }) => (
  <code className="rounded bg-dt-surface-warm px-1.5 py-0.5 text-xs text-dt-burnt-orange">{children}</code>
);
const Example = ({ children }: { children: ReactNode }) => (
  <div className="rounded-lg border border-dt-border bg-dt-cream/50 p-3 text-sm text-dt-text-primary">{children}</div>
);

export const GUIDE_SECTIONS: GuideSection[] = [
  {
    id: "overview",
    title: "Overview",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>
          DijiOne separates two concerns that are easy to conflate: proving who a person is, and deciding what they
          may do once they are in.
        </P>
        <Quote>
          Entra confirms who the user is.
          <br />
          DijiOne determines what the user can access.
        </Quote>
        <P>
          Microsoft Entra ID authenticates the user — sign-in, MFA, session lifecycle. Once signed in, the Admin
          Center is where administrators manage everything about <em>business authorization</em>: which
          applications a user can open, which role they hold in each, and which clients or portfolios their access
          is scoped to.
        </P>
      </div>
    ),
  },
  {
    id: "access-model",
    title: "Access Model",
    module: "platform",
    body: (
      <P>
        The diagram above traces the full chain from sign-in to a working application screen. Read it top to
        bottom: authentication happens once, then access flows either directly to a user or through a group, and
        both paths resolve into the same Effective Access before a business application is reachable.
      </P>
    ),
  },
  {
    id: "users",
    title: "Users",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>Users represent authorized DijiOne identities. From a user&rsquo;s detail page, administrators can review:</P>
        <Ul>
          <li>Account status (active / inactive)</li>
          <li>Platform role (Platform User, Platform Admin, Super Admin)</li>
          <li>Application access</li>
          <li>Group memberships</li>
          <li>Client access</li>
          <li>Effective access</li>
          <li>Audit history</li>
        </Ul>
        <P>Use user-centric administration when:</P>
        <Ul>
          <li>Onboarding a new person</li>
          <li>Changing someone&rsquo;s role</li>
          <li>Troubleshooting &ldquo;why can&rsquo;t this person see X&rdquo;</li>
          <li>Offboarding — deactivating access on departure</li>
        </Ul>
      </div>
    ),
  },
  {
    id: "applications",
    title: "Applications",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>Applications are the business modules registered in DijiOne. Current registry:</P>
        <Ul>
          <li>
            <strong>DijiTalentFlow</strong> — fully implemented Talent Operations and Client Tracking module.
          </li>
          <li>
            <strong>DijiBirthday</strong> — registered as Coming Soon; no functional workflows yet.
          </li>
          <li>
            <strong>DijiSpark</strong> — registered as Coming Soon; no functional workflows yet.
          </li>
        </Ul>
        <P>
          Application-centric administration starts from an application and asks who can reach it. Access to an
          application may come directly (a user is assigned to it) or through a group the user belongs to.
        </P>
      </div>
    ),
  },
  {
    id: "groups",
    title: "Groups",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>
          Groups are reusable access containers. Instead of assigning the same application, role and client scope
          to ten people individually, assign it once to a group and add members to it.
        </P>
        <Example>
          <strong>TA Team</strong>
          <br />→ DijiTalentFlow
          <br />→ Talent Acquisition Member
          <br />→ Selected Clients / All Clients
        </Example>
        <P>Members inherit the group&rsquo;s valid grants automatically. Groups should normally be preferred over large numbers of direct user assignments — they stay correct as people join and leave a team.</P>
      </div>
    ),
  },
  {
    id: "roles",
    title: "Roles",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>A role represents a business responsibility and bundles the permissions needed to perform it. DijiOne ships these roles:</P>
        <Ul>
          <li><strong>Super Admin</strong> — full platform administration, including managing other administrators.</li>
          <li><strong>Platform Admin</strong> — manages ordinary users, module access, roles and client scope, but not other administrators.</li>
          <li><strong>Talent Acquisition Member</strong> — DijiTalentFlow staff with cross-client operational access.</li>
          <li><strong>Customer Success</strong> — TA Member access plus the right to review incoming talent requests.</li>
          <li><strong>TA Manager</strong> — TA Member permissions plus review rights and cross-client oversight.</li>
          <li><strong>Talent Client</strong> — external client user scoped to their own organization&rsquo;s requests.</li>
        </Ul>
      </div>
    ),
  },
  {
    id: "permissions",
    title: "Permissions",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>Permissions are the smallest fine-grained capabilities in the system — the atoms roles are built from. Examples:</P>
        <Ul>
          <li><Code>talent.requests.read</Code> — View All Requests</li>
          <li><Code>talent.candidates.read</Code> — View Candidate Pool</li>
          <li><Code>talent.interviews.manage</Code> — Manage Interviews</li>
          <li><Code>platform.admin.manage_users</Code> — Manage Users</li>
        </Ul>
        <Quote>Permissions are normally combined into roles and are not usually assigned directly to everyday users.</Quote>
        <Quote>Most day-to-day access administration should be performed through Users, Groups, Applications, Roles and Client Scope.</Quote>
      </div>
    ),
  },
  {
    id: "client-scope",
    title: "Client / Portfolio Scope",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>Role and Client Scope answer two different questions:</P>
        <div className="grid gap-3 sm:grid-cols-2">
          <Example><strong>Role</strong> answers: &ldquo;What can the user do?&rdquo;</Example>
          <Example><strong>Client Scope</strong> answers: &ldquo;Where can the user do it?&rdquo;</Example>
        </div>
        <Example>
          Talent Acquisition Member
          <br />+ ABC Company
          <br />+ XYZ Company
        </Example>
        <P>
          A scope may instead be set to <Code>ALL_CLIENTS</Code>, granting the role across every client rather than
          a specific list. Regardless of what the UI shows, tenant/client isolation is enforced server-side —
          hiding a control in the frontend is never the security boundary.
        </P>
      </div>
    ),
  },
  {
    id: "direct-vs-inherited",
    title: "Direct vs Inherited Access",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Example><strong>Direct</strong> — an explicit assignment made on the user record itself.</Example>
          <Example><strong>Inherited</strong> — access that flows from Access Group membership.</Example>
        </div>
        <P>DijiOne currently uses an additive allow model:</P>
        <Ul>
          <li>Valid client scopes from every source combine together.</li>
          <li><Code>ALL_CLIENTS</Code> takes precedence wherever it is granted.</li>
          <li>There is no explicit DENY model in the current release — access only ever adds up, it is never subtracted by a conflicting rule.</li>
        </Ul>
      </div>
    ),
  },
  {
    id: "effective-access",
    title: "Effective Access",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>Effective Access is the final authorization result — what a user can actually do right now — calculated from:</P>
        <Ul>
          <li>Account status</li>
          <li>Platform role</li>
          <li>Direct assignments</li>
          <li>Group memberships</li>
          <li>Application role</li>
          <li>Permissions</li>
          <li>Client scope</li>
        </Ul>
        <P>
          The Effective Access view on a user&rsquo;s page also shows <strong>Access Sources</strong> — a plain-language
          answer to &ldquo;why does this person have this access?&rdquo;, tracing each grant back to a direct assignment or a
          specific group.
        </P>
      </div>
    ),
  },
  {
    id: "common-tasks",
    title: "Common Admin Tasks",
    module: "platform",
    body: (
      <Ol>
        <li>
          <strong>Give a user DijiTalentFlow access directly</strong> — open the user, add a module assignment for
          DijiTalentFlow, choose a role and client scope.
        </li>
        <li><strong>Add a user to a Group</strong> — open the group, use the member selector to search by name or email, then Add.</li>
        <li><strong>Give a Group application access</strong> — open the group, find the application under Application Access, enable it and choose a role.</li>
        <li><strong>Assign an application role</strong> — set the Role field on a user&rsquo;s or group&rsquo;s module assignment.</li>
        <li><strong>Restrict access to selected clients</strong> — uncheck All Clients on the module assignment and pick specific clients.</li>
        <li><strong>Grant All Clients</strong> — check All Clients on the module assignment.</li>
        <li><strong>Check Effective Access</strong> — open the user&rsquo;s Effective Access tab to see the resolved result and its sources.</li>
        <li><strong>Understand Direct vs Inherited access</strong> — see the section above; Access Sources on a user&rsquo;s page labels each grant.</li>
        <li><strong>Remove application access</strong> — remove the module assignment on the user or group.</li>
        <li><strong>Remove a user from a group</strong> — open the group&rsquo;s Members list and use Remove on their row.</li>
        <li><strong>Deactivate a group</strong> — use the Deactivate action on the group page (system groups are protected).</li>
        <li><strong>Deactivate/offboard a user</strong> — set the user&rsquo;s account status to inactive on their detail page.</li>
        <li><strong>Review administrative changes</strong> — open Audit to see who changed what and when.</li>
      </Ol>
    ),
  },
  {
    id: "recommendation",
    title: "Access Management Recommendation",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>Preferred model — assign access through groups, not individuals:</P>
        <Example>User → Group → Application → Role → Client Scope</Example>
        <P>Direct user assignments should generally be reserved for exceptions, temporary access, and special cases — not as the default way to grant access.</P>
      </div>
    ),
  },
  {
    id: "authentication",
    title: "Authentication / SSO",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>
          Development currently runs in <strong>Dev Identity Mode</strong> unless real Microsoft Entra ID has been
          activated for this environment — a persona switcher stands in for sign-in so the platform can be built
          and demoed before production credentials exist.
        </P>
        <P>Microsoft Entra ID is the intended production SSO provider. No claim is made here that live production SSO is active; check with a platform administrator for this environment&rsquo;s current state.</P>
      </div>
    ),
  },
  {
    id: "service-isolation",
    title: "Service Isolation",
    module: "platform",
    body: (
      <div className="flex flex-col gap-3">
        <P>DijiOne is built from independently runnable services rather than one monolith:</P>
        <Ul>
          <li>DijiOne Shell — the home/gateway experience</li>
          <li>Admin Center — this application</li>
          <li>DijiTalentFlow, DijiBirthday, DijiSpark — business modules</li>
        </Ul>
        <P>Each is a separate service boundary. In plain terms: a failure in one business application should not take down the whole platform.</P>
      </div>
    ),
  },
  {
    id: "troubleshooting",
    title: "Troubleshooting",
    module: "platform",
    body: (
      <div className="flex flex-col gap-4">
        <div>
          <p className="mb-1.5 text-sm font-semibold text-dt-text-primary">User cannot see an application</p>
          <Ul>
            <li>Confirm the user&rsquo;s account is active</li>
            <li>Inspect direct module assignment</li>
            <li>Inspect group membership</li>
            <li>Inspect the group&rsquo;s application access</li>
            <li>Inspect the assigned role</li>
            <li>Inspect client scope</li>
            <li>Check Effective Access</li>
            <li>Ask the user to sign out and back in — a token refresh may be required</li>
          </Ul>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-semibold text-dt-text-primary">User can see the wrong client</p>
          <Ul>
            <li>Inspect Effective Access</li>
            <li>Check Direct vs Inherited access sources</li>
            <li>Verify whether ALL_CLIENTS is granted anywhere</li>
            <li>Review group scope</li>
          </Ul>
        </div>
        <div>
          <p className="mb-1.5 text-sm font-semibold text-dt-text-primary">Group member is not inheriting access</p>
          <Ul>
            <li>Check the group&rsquo;s status (active/inactive)</li>
            <li>Confirm membership</li>
            <li>Confirm the group&rsquo;s application assignment</li>
            <li>Check role and scope</li>
            <li>Ask the user to sign in again to refresh their token</li>
          </Ul>
        </div>
      </div>
    ),
  },
  {
    id: "security-notes",
    title: "Security Notes",
    module: "platform",
    body: (
      <Ul>
        <li>Frontend visibility is not the security boundary.</li>
        <li>Backend services enforce access on every request.</li>
        <li>Permissions and client scope are validated server-side, not just hidden in the UI.</li>
        <li>Use least privilege — grant only what a role genuinely needs.</li>
        <li>Prefer groups over direct assignment for maintainability.</li>
        <li>Use Audit to trace who changed what access, and when.</li>
      </Ul>
    ),
  },
];
