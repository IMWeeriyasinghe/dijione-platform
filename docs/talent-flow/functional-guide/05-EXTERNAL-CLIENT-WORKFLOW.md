# 05: External client access and the client portal

[Start](00-START-HERE.md) · prev [04 Lever and candidate workflow](04-LEVER-AND-CANDIDATE-WORKFLOW.md) · next [06 Screen-by-screen guide](06-SCREEN-BY-SCREEN-GUIDE.md)

Clients have **no DijiOne account**. TA gives a client contact a private, time-limited **access link**. It opens a separate, read-only **Client Talent Review Workspace** (the client portal), showing only that client's requests and the candidates TA has shared. Colours follow the [legend](00-START-HERE.md#how-to-read-the-diagrams).

> Every action here is 🔑 **External access**: it changes what someone outside Dijital Team can see. Production has one active link (Access4, open item 1); do not issue, change or revoke links in Production without approval.

| Section | Diagram | Screens | UAT |
|---|---|---|---|
| [E1](#e1-access-link-lifecycle) | Access-link lifecycle | [S20](06-SCREEN-BY-SCREEN-GUIDE.md#s20-client-access-links) | [U9](07-GUIDED-WALKTHROUGH-AND-UAT.md#u9-external-access-link-management) |
| [E2](#e2-what-happens-when-the-client-opens-the-link) | Opening the link | [S22](06-SCREEN-BY-SCREEN-GUIDE.md#s22-portal-access-page)–[S28](06-SCREEN-BY-SCREEN-GUIDE.md#s28-portal-interviews) | [U10](07-GUIDED-WALKTHROUGH-AND-UAT.md#u10-client-portal-access) |
| [E3](#e3-what-the-client-can-and-cannot-see) | What the client can and cannot see | [S24](06-SCREEN-BY-SCREEN-GUIDE.md#s24-portal-overview)–[S28](06-SCREEN-BY-SCREEN-GUIDE.md#s28-portal-interviews) | [U8](07-GUIDED-WALKTHROUGH-AND-UAT.md#u8-candidate-visibility-restrictions) |
| [E4](#e4-sharing-and-withdrawing-candidates) | Sharing and withdrawing candidates | [S14](06-SCREEN-BY-SCREEN-GUIDE.md#s14-talent-request-detail), [S17](06-SCREEN-BY-SCREEN-GUIDE.md#s17-applications) | [U8](07-GUIDED-WALKTHROUGH-AND-UAT.md#u8-candidate-visibility-restrictions) |

---

## E1. Access-link lifecycle

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 330}}}%%
flowchart LR
    G["① TA: Client Access Links<br/>choose client, optional contact,<br/>expiry 1 to 90 days (default 14)"]:::ta --> GEN["② Generate access link"]:::ta
    GEN --> ONCE["Link shown once:<br/>Copy link"]:::auto
    ONCE --> SEND["③ TA sends it personally;<br/>DijiOne sends no email"]:::ta
    SEND --> OPEN(["④ Client contact<br/>opens the link"]):::client
    OPEN --> USE["⑤ Portal usable until the link<br/>expires or is revoked"]:::client
    USE -.-> EXT["Extend: same link,<br/>new expiry date"]:::ta
    USE -.-> REG["Regenerate: old link revoked,<br/>new link shown once"]:::ta
    USE -.-> REV["Revoke: ends access<br/>at the next page load"]:::stop

    classDef ta fill:#FFE8D6,stroke:#C9431D,stroke-width:1.5px,color:#24140F
    classDef auto fill:#ECEFF3,stroke:#5B6472,stroke-width:1.5px,color:#24140F
    classDef client fill:#E2F3E8,stroke:#138A4B,stroke-width:1.5px,color:#24140F
    classDef stop fill:#FBE0DE,stroke:#C62D26,stroke-width:1.5px,stroke-dasharray:5 3,color:#24140F
```

```mermaid
stateDiagram-v2
    direction LR
    state "Active" as A
    state "Expired" as E
    state "Revoked" as R
    [*] --> A: Generate
    A --> A: Extend
    A --> E: expiry date passes
    E --> A: Extend
    A --> R: Revoke or Regenerate
    E --> R: Revoke or Regenerate
    R --> [*]

    classDef ok fill:#E2F3E8,stroke:#138A4B,color:#24140F
    classDef off fill:#FBE0DE,stroke:#C62D26,color:#24140F
    class A ok
    class E, R off
```

| | |
|---|---|
| **Purpose** | Give one client contact secure, revocable, read-only access without creating an account |
| **Who uses it** | Any TA staff member, for clients in their scope |
| **How it starts** | DijiTalentFlow → **Client Access Links** |
| **Main actions** | Choose **Client** (required); **Contact name** and **Contact email** are optional and for records only. Set **Expires on** (1 to 90 days ahead; default 14). **Generate access link** 🔑, then **Copy link** and send it yourself. Per row: **Extend** (choose a new date → **Save**) 🔑, **Regenerate** 🔑, **Revoke** 🔑 |
| **Decision points** | How long should the client have access? Should an existing link be extended, replaced or revoked? |
| **Expected outcome** | The table shows the link with status **Active**, its expiry date ("in N days", amber at 3 days or fewer), when it was first redeemed, when it was last used, and how many times it has been used |
| **Restrictions and errors** | **The full link is shown only once.** You can re-copy it until you leave the browser session; after that the server cannot show it again, so use **Regenerate** for a new one. A link can be reused until it expires or is revoked; it is not single-use. **Revoke** acts immediately, with no confirmation. A revoked link cannot be extended; regenerate it. An expired link *can* be extended, which re-activates the same link. Expiry can never be indefinite |
| **Screens** | [S20 Client Access Links](06-SCREEN-BY-SCREEN-GUIDE.md#s20-client-access-links) |

---

## E2. What happens when the client opens the link

```mermaid
sequenceDiagram
    autonumber
    actor CL as Client contact
    participant PO as Client portal
    participant TF as DijiTalentFlow
    CL->>PO: Opens the access link
    PO->>PO: Removes the secret part from the address bar
    PO->>TF: Is this link valid?
    alt Active
        TF-->>PO: 45-minute session for this client only
        PO-->>CL: Overview of "Your engagement"
        loop Every page the client opens
            PO->>TF: Request with session
            TF->>TF: Re-check link: not revoked, not expired
            TF-->>PO: Only this client's data
        end
        Note over PO,TF: After 45 minutes the portal quietly renews the<br/>session from the same link, while the link is still valid
    else Expired, revoked or unknown
        TF-->>PO: Refused
        PO-->>CL: This access link is invalid or has expired
    end
```

| | |
|---|---|
| **Purpose** | Let the client in safely, and shut them out the moment the link stops being valid |
| **Who uses it** | The client contact |
| **How it starts** | Clicking the link, whose address ends in `/access#…` |
| **Main actions** | None: the portal opens automatically ("Opening your workspace…") |
| **Expected outcome** | The **Overview** page, titled "Your engagement — *Client name*" |
| **Restrictions and errors** | Invalid, expired or revoked links show *"This access link is invalid or has expired. Ask your Dijital Team contact to send you a new link."* The session belongs to **that browser tab**: a new tab or window shows "Use the access link your Dijital Team contact sent you…" until the link is opened again. **Sign out** ends the session in that tab. Each opening and renewal adds to the link's **Uses** count. Repeated attempts are rate-limited |
| **Screens** | [S22 Access page](06-SCREEN-BY-SCREEN-GUIDE.md#s22-portal-access-page) · [S23 No session](06-SCREEN-BY-SCREEN-GUIDE.md#s23-portal-no-session-page) · [S24 Overview](06-SCREEN-BY-SCREEN-GUIDE.md#s24-portal-overview) |

---

## E3. What the client can and cannot see

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 330}}}%%
flowchart TB
    Q(["Client opens a portal page"]):::client --> C1{"Link still valid?<br/>Not expired, not revoked"}:::decision
    C1 -->|No| X1["Refused"]:::stop
    C1 -->|Yes| C2{"Does the request belong<br/>to this link's client?"}:::decision
    C2 -->|No| X2["Not found; other clients'<br/>data is never shown"]:::stop
    C2 -->|Yes| R["Request shown: title, stage, progress,<br/>client-facing status text"]:::client
    R --> C3{"Has TA ticked<br/>Client Visible?"}:::decision
    C3 -->|No| X3["Candidate not listed"]:::stop
    C3 -->|Yes| CAN["Candidate shown: name, title, skills,<br/>experience summary, stage"]:::client
    CAN --> C4{"Interview ticked<br/>Visible to client?"}:::decision
    C4 -->|No| X4["Interview not listed"]:::stop
    C4 -->|Yes| INT["Interview shown: date, type,<br/>status, meeting link"]:::client

    classDef client fill:#E2F3E8,stroke:#138A4B,stroke-width:1.5px,color:#24140F
    classDef decision fill:#FFF3CD,stroke:#C78300,stroke-width:1.5px,color:#24140F
    classDef stop fill:#FBE0DE,stroke:#C62D26,stroke-width:1.5px,stroke-dasharray:5 3,color:#24140F
```

| | |
|---|---|
| **Purpose** | Guarantee that a client sees only curated information about its own roles |
| **Portal pages** | **Overview**: Active requests, Candidates in process, Interviews this week, Offers in progress, and "Your requests". **Requests**: the list. **Request detail**: stage timeline, progress, and "Candidates shared with you (N)". **Candidate**: profile, read only. **Interviews** |
| **Never shown** | Hidden candidates; email, phone, location and source; internal notes, scores, TA and Customer Success status, priority; messages and documents; Lever tags and posting matches; other clients' data |
| **Interaction** | **None in V1.** The client cannot comment, approve, reject, request interviews, message or upload. Feedback happens outside DijiOne |
| **Restrictions and errors** | A candidate who is un-shared, or whose link stops working, shows "Candidate not found: this candidate is no longer shared with you, or the link is no longer valid" |
| **Screens** | [S24](06-SCREEN-BY-SCREEN-GUIDE.md#s24-portal-overview) · [S25](06-SCREEN-BY-SCREEN-GUIDE.md#s25-portal-requests) · [S26](06-SCREEN-BY-SCREEN-GUIDE.md#s26-portal-request-detail) · [S27](06-SCREEN-BY-SCREEN-GUIDE.md#s27-portal-candidate-review) · [S28](06-SCREEN-BY-SCREEN-GUIDE.md#s28-portal-interviews) |

---

## E4. Sharing and withdrawing candidates

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 330}}}%%
flowchart LR
    T(["TA on a request's Candidates tab<br/>or on Applications"]):::ta --> Q{"Client Visible"}:::decision
    Q -->|"Tick"| ON["Saved at once<br/>and audited"]:::auto --> SEE(["Client sees the candidate<br/>on the next page"]):::client
    Q -->|"Untick"| OFF["Saved at once<br/>and audited"]:::auto --> GONE["Candidate disappears;<br/>direct address refused"]:::stop
    W["Posting unmapped or moved<br/>to another client"]:::ta --> ALL["Every candidate on that<br/>request is un-shared"]:::stop

    classDef ta fill:#FFE8D6,stroke:#C9431D,stroke-width:1.5px,color:#24140F
    classDef auto fill:#ECEFF3,stroke:#5B6472,stroke-width:1.5px,color:#24140F
    classDef client fill:#E2F3E8,stroke:#138A4B,stroke-width:1.5px,color:#24140F
    classDef decision fill:#FFF3CD,stroke:#C78300,stroke-width:1.5px,color:#24140F
    classDef stop fill:#FBE0DE,stroke:#C62D26,stroke-width:1.5px,stroke-dasharray:5 3,color:#24140F
```

| | |
|---|---|
| **Purpose** | TA decides, candidate by candidate, what each client sees |
| **Who uses it** | TA staff, for clients in scope |
| **Main actions** | Tick or untick **Client Visible** 🔑 |
| **Expected outcome** | The change applies from the client's next page load. Every new candidate from Lever starts hidden |
| **Restrictions and errors** | No confirmation step. A failed save flips the box back and shows "Candidate sharing could not be updated". Un-matching or moving a posting un-shares everything on its request |
| **Screens** | [S14 Candidates tab](06-SCREEN-BY-SCREEN-GUIDE.md#s14-talent-request-detail) · [S17 Applications](06-SCREEN-BY-SCREEN-GUIDE.md#s17-applications) |

Continue with [06 Screen-by-screen guide](06-SCREEN-BY-SCREEN-GUIDE.md).
