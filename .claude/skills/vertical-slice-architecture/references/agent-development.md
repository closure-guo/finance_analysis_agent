# VSA for AI Agent Development

## Mapping: Slice vs Agent vs Tool

These are three different abstraction layers that work together:

| Dimension | Vertical Slice | Agent | Tool |
|-----------|---------------|-------|------|
| Essence | Code organization unit | Autonomous decision-maker | Concrete execution capability |
| Granularity | One feature/use case | One domain/module | One callable function |
| Example | `CreateOrder.cs` | Order Domain Agent | `send_email()` |
| Lifecycle | Static code file | Runtime session/process | Registered capability |

**The relationship:** An Agent owns multiple slices. A slice's handler calls multiple Tools.

```
Agent (Order Domain)
  ├── Slice: CreateOrder  ──────► Tool: charge_payment()
  ├── Slice: GetOrder     ──────► Tool: cache_get()
  ├── Slice: CancelOrder  ──────► Tool: send_email()
  └── Slice: ShipOrder    ──────► Tool: publish_event()
```

**Analogy:** Agent is the "engineer", slice is the "blueprint+implementation of one feature", tool is the "wrench or screwdriver".

**Why slice != Agent:** If each slice were an Agent, the Agent would be too narrow -- unable to understand the domain context needed to make design decisions (naming conventions, entity relationships, business rules).

**Why slice != Tool:** A Tool is a stateless function (input->execute->output). A slice contains a full business workflow: validation->load domain model->enforce business rules->persist->publish events.

## Why VSA Fits AI Agents

VSA aligns naturally with how AI agents work:

1. **Bounded context per task** -- Each slice is self-contained. An agent can implement a complete feature by reading/writing files in a single folder, without needing full system knowledge.
2. **Additive development** -- Agents add features by creating new slices. No risk of breaking unrelated existing code. No need to understand global architecture to add a feature.
3. **Local reasoning** -- An agent only needs the content of one slice + the shared kernel to implement or modify a feature. Layered architectures require the agent to understand and navigate across Controller/Service/Repository/DTO layers.
4. **Parallel agent work** -- Multiple agents can each own different slices simultaneously without conflicts, since slices are independent by design.

## Agent-Specific Workflow

### Discovery Phase

Before writing code, the agent must discover existing slices:

1. **List feature folders** -- Read the `Features/` directory to understand what exists
2. **Read 2-3 representative slices** -- Pick one simple CRUD slice, one complex slice, and one query-only slice to understand conventions
3. **Check shared infrastructure** -- Read `Common/` or `SharedKernel/` to understand Result types, behaviors, base classes
4. **Check domain model** -- Read `Domain/` to understand entities and their business rules

```
Agent workflow on receiving "Add ability to cancel orders":
1. Read Features/ directory -> sees Orders/ contains CreateOrder, GetOrder, UpdateOrder
2. Read CreateOrder.cs and GetOrder.cs -> learns naming conventions, patterns
3. Read Domain/Order.cs -> understands Order entity, its Status enum, business rules
4. Read Common/Result.cs -> understands Result<T> pattern used
5. Write Features/Orders/CancelOrder.cs -> complete self-contained slice
6. Register endpoint -> update or auto-discover
```

### Implementation Phase

**For each new slice, the agent follows this template:**

```csharp
// 1. Static class with same name as the feature action
public static class {Action}{Entity}
{
    // 2. Command or Query record (named "Command" or "Query" inside the static class)
    public record Command(...) : IRequest<Result<{ResponseType}>>;

    // 3. Response DTO record (if needed)
    public record Response(...);

    // 4. FluentValidation validator (business rules, not just format)
    public class Validator : AbstractValidator<Command> { ... }

    // 5. Handler with primary constructor injection
    public class Handler(AppDbContext db, ILogger<Handler> logger, [other capabilities])
        : IRequestHandler<Command, Result<...>>
    {
        public async Task<Result<...>> Handle(Command req, CancellationToken ct)
        {
            // 5a. Load aggregates from DB
            // 5b. Execute domain behavior (push business logic to entities)
            // 5c. Save changes
            // 5d. Publish domain events if needed
            // 5e. Return result
        }
    }

    // 6. Endpoint registration
    public class Endpoint : IEndpoint { ... }
}
```

### Critical Rules for Agents

1. **Never modify existing slices when adding a new one** -- If you need data from another feature, query the database directly, do not call another slice's handler.

2. **Follow existing conventions exactly** -- If existing slices use `Result<T>`, use it. If they use records for commands, use records. Consistency is more important than personal preference.

3. **Push business logic to domain entities** -- Do not put validation rules that belong in the domain (state transitions, invariants) in the handler. Check the entity for existing methods:
   ```csharp
   // Good: Use domain method
   order.Cancel();  // Domain entity enforces "can only cancel Pending orders"
   
   // Bad: Business logic in handler
   if (order.Status != OrderStatus.Pending) return Result.Failure(...);
   order.Status = OrderStatus.Cancelled;
   ```

4. **Query the database directly** -- Each slice owns its own queries. Do not reuse another slice's query logic:
   ```csharp
   // Good: Slice queries what it needs
   var order = await db.Orders.Include(o => o.Items).FirstAsync(o => o.Id == req.OrderId, ct);
   
   // Bad: Calling another slice's handler
   var order = await mediator.Send(new GetOrder.Query(req.OrderId)); // NEVER
   ```

5. **Minimal shared kernel** -- When in doubt, duplicate code between slices rather than extracting. Only extract when you see the exact same code in 3+ slices with the same reason to change.

6. **One feature = one slice file/folder** -- The agent should create exactly one new file (or folder) per feature. If the feature feels like it needs multiple slices, it might actually be multiple features.

## Common Agent Mistakes with VSA

### Mistake 1: Recreating Layered Architecture Inside Slices

Agent sees a slice and thinks "I need a service layer and repository pattern" -- creating mini-layers within the slice.

**Fix:** Handler talks directly to `DbContext`. No repository interface needed. Only add indirection when that specific slice has a concrete need (e.g., raw SQL performance).

### Mistake 2: Extracting Too Early

Agent sees similar code in two slices and immediately creates a shared abstraction.

**Fix:** Duplicate the code. Wait for 3 instances. The two slices might evolve differently.

### Mistake 3: Anemic Domain Model

Agent puts all business logic in handlers and leaves entities as property bags.

**Fix:** Check existing entities for behavior methods. Add methods to entities for state transitions and business rules. Handlers orchestrate; entities enforce rules.

### Mistake 4: Cross-Slice Direct Calls

Agent uses `_mediator.Send(new OtherSlice.Command(...))` to reuse logic.

**Fix:** Query the DB directly for reads. Use `IPublisher.Publish(new DomainEvent(...))` for triggering side effects in other slices.

### Mistake 5: Over-Complicating Queries

Agent creates complex mapping profiles or repositories for simple queries.

**Fix:** For simple reads, use `ProjectTo<TDto>` or manual `Select()` in the query. Each query slice can use the simplest approach that works for its specific needs.

## Agent-Friendly VSA Project Checklist

Before starting VSA development, ensure the project has these conventions established (the agent should read these first):

- [ ] `Result<T>` type defined in `Common/Models/`
- [ ] `IEndpoint` marker interface and auto-registration in `Program.cs`
- [ ] MediatR pipeline behaviors registered (validation, logging)
- [ ] Folder structure convention documented (single-file vs folder-per-feature)
- [ ] Naming convention: `{Action}{Entity}.cs` (e.g., `CreateOrder.cs`, not `OrderController.cs`)
- [ ] At least 2 reference slices showing patterns for commands and queries
- [ ] Domain entities with behavior methods (not just properties)
- [ ] `AppDbContext` accessible via DI with `DbSet<T>` for all aggregates

## Multi-Agent VSA Development

Agents map to **bounded contexts** (domains), not individual slices. Each agent owns a group of related slices.

```
Project
├── Agent: Order Domain          ──────── owns ────────►
│   ├── Slice: CreateOrder                            │
│   ├── Slice: GetOrder                               │  These agents
│   ├── Slice: CancelOrder                            │  work in parallel
│   └── Slice: ShipOrder                              │  without conflicts
│                                                     │
├── Agent: Product Domain        ──────── owns ───────►
│   ├── Slice: CreateProduct                          │
│   ├── Slice: GetProduct                             │
│   └── Slice: UpdateInventory                        │
│                                                     │
├── Agent: Customer Domain       ──────── owns ───────►
│   ├── Slice: RegisterCustomer                       │
│   └── Slice: GetCustomerProfile                     │
│                                                     │
└── Shared Infrastructure (managed by one designated agent)
    ├── Common/Result.cs, Error.cs
    ├── MediatR Pipeline Behaviors
    └── DbContext / Infrastructure
```

### Collaboration Rules

1. **Each agent owns all slices in one bounded context** -- An Order Agent owns every Order-related slice. Never split one domain's slices across multiple agents.

2. **Agents communicate via events, not direct calls** -- When Order Agent needs Inventory to reserve stock, it publishes `OrderCreatedEvent`. The Inventory Agent handles it. They never call each other's handlers.

3. **Both agents need a new shared capability** -- One agent creates the capability interface in `Common/` (e.g., `IEmailSender`). Both use it. Implementation goes in `Infrastructure/`.

4. **Cross-domain data queries** -- Agent A queries the database directly for read-only data from Agent B's domain. No handler calls between agents.

5. **Domain entity changes** -- When an entity needs a new behavior method, the owning agent modifies it. Other agents can use the new method in their slices after it's merged.

6. **Shared kernel is read-only for most agents** -- Designate one "platform agent" to manage `Common/`, `Infrastructure/`, and shared conventions. Feature agents treat it as read-only.

### What Counts as a "Tool" in This Model

Tools are external capabilities an Agent calls while implementing a slice:

| Tool Category | Examples | Used In |
|--------------|----------|---------|
| Communication | `send_email()`, `send_sms()`, `push_notification()` | Order confirmation, shipping notification |
| Payment | `charge_payment()`, `refund_payment()` | CreateOrder, CancelOrder |
| Storage | `upload_file()`, `generate_pdf()`, `store_blob()` | Invoice generation, receipt creation |
| External APIs | `get_exchange_rate()`, `verify_address()` | Pricing, shipping calculation |
| Infrastructure | `publish_event()`, `cache_set()`, `enqueue_job()` | Cross-slice communication, performance |

**Agent implements a slice -> Handler contains business logic -> Handler calls Tools for external effects**

## Example Agent Session

```
User: "Add the ability for users to mark orders as shipped"

Agent:
1. Read Features/Orders/ -> sees CreateOrder.cs, GetOrder.cs, CancelOrder.cs
2. Read Domain/Order.cs -> sees Order has Status (Pending, Confirmed, Shipped, Delivered, Cancelled)
3. Read CancelOrder.cs -> learns pattern: Command record, Validator, Handler, Endpoint
4. Check if Order has a Ship() method -> it doesn't
5. Add Ship() method to Order.cs domain entity:
   public Result Ship()
   {
       if (Status != OrderStatus.Confirmed) 
           return Result.Failure("Order.NotConfirmed", "Only confirmed orders can be shipped");
       Status = OrderStatus.Shipped;
       AddDomainEvent(new OrderShippedEvent(Id));
       return Result.Success();
   }
6. Create Features/Orders/ShipOrder.cs:
   - ShipOrder.Command record with OrderId
   - Validator ensuring OrderId is valid
   - Handler loading Order, calling order.Ship(), saving, returning Result
   - Endpoint mapping PUT /api/orders/{id}/ship
7. Verify: new file created, existing files untouched (except Order.cs)
```
