# VSA Anti-Patterns & Common Pitfalls

## 1. Premature Abstraction (The DRY Trap)

**Symptom:** Extracting shared code at the first sign of duplication.

**Problem:** Two pieces of code look identical today but evolve differently tomorrow. Shared abstractions create coupling.

**Example:** `ProcessPayment` and `RefundPayment` share validation. Extracted into `PaymentValidator`. Three months later refunds need different rules -- now you have conditional logic in the shared validator.

**Fix:** Follow WET (Write Everything Twice). Wait for three instances of true duplication with the same reason to change.

## 2. Base Handler Pyramid (Inheritance Over Composition)

**Symptom:** Creating abstract base handler classes to "share common code."

```csharp
// ANTI-PATTERN
public abstract class BaseHandler<TRequest, TResponse> : IRequestHandler<TRequest, TResponse>
{
    protected readonly AppDbContext Context;
    protected readonly ILogger Logger;
    protected abstract Task<TResponse> HandleCore(TRequest request, CancellationToken ct);

    protected BaseHandler(AppDbContext context, ILogger logger) { ... }

    protected virtual Task ValidateAsync(TRequest request) => Task.CompletedTask;

    public async Task<TResponse> Handle(TRequest request, CancellationToken ct)
    {
        await ValidateAsync(request);  // forced on ALL handlers
        Logger.LogInformation("Handling...");
        return await HandleCore(request, ct);
    }
}
```

**Problem:** Hidden coupling. One handler needs to skip validation? Add conditional logic. Need different logging? Override. Base class grows into a god class.

**Fix:** Use MediatR pipeline behaviors for cross-cutting concerns. Compose dependencies per handler.

## 3. Feature Factory (No System Thinking)

**Symptom:** Each feature is built in isolation without considering overall domain design.

**Problem:** You lose sight of broader domain concepts. Everything is a Transaction Script. Domain model becomes anemic. No shared understanding of core entities.

**Fix:** Identify core domain entities early. Push business rules into rich domain models. Use Domain Events for cross-slice coordination. Have periodic architecture reviews.

## 4. God Slice (Transaction Script Gone Wrong)

**Symptom:** A single slice handler grows to 500+ lines doing everything.

```csharp
// ANTI-PATTERN: Handler doing too much
public class ProcessOrderHandler : IRequestHandler<Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        // 50 lines: validate order
        // 80 lines: calculate pricing with discounts
        // 30 lines: check inventory
        // 40 lines: process payment
        // 60 lines: create shipment records
        // 40 lines: send email notifications
        // 30 lines: update analytics
        // ... 400+ lines total
    }
}
```

**Problem:** Violates Single Responsibility. Hard to test. Hard to understand. Changes risk breaking everything.

**Fix:** Refactor by extracting domain services. Push logic into entities. Use Domain Events to decouple side effects.

## 5. Shared Slice Database Dependencies

**Symptom:** Slices directly calling each other via `_mediator.Send(new OtherSlice.Command(...))`.

**Problem:** Tight coupling, distributed transaction risk, violating slice autonomy.

**Fix:** Each slice queries its own data. Cross-slice communication via Domain Events (same module) or Integration Events (across modules).

## 6. Anemic Domain Model with Fat Handlers

**Symptom:** All business logic lives in handlers. Domain entities are just property bags.

```csharp
// ANTI-PATTERN
public class Order  // Anemic entity
{
    public Guid Id { get; set; }
    public OrderStatus Status { get; set; }
    public List<OrderItem> Items { get; set; } = new();
}

// Handler contains ALL business logic
public class SubmitOrderHandler : IRequestHandler<Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        var order = await db.Orders.FindAsync(req.OrderId);
        if (order.Status != OrderStatus.Pending) return Result.Failure("...");
        if (!order.Items.Any()) return Result.Failure("...");
        // ... more validation logic that should be in the entity
        order.Status = OrderStatus.Submitted;
    }
}
```

**Fix:** Push validation and state transition rules into the domain entity. Handlers should orchestrate, not contain business rules.

## 7. Premature Clean Architecture in Slices

**Symptom:** Within each slice, creating mini-layers (SliceController -> SliceService -> SliceRepository).

**Problem:** Recreating the layered architecture problem inside each slice. Defeats the purpose of VSA.

**Fix:** Handler talks directly to DbContext (or raw SQL, Dapper, etc.). Slice IS the layer. Only add abstraction when the specific slice needs it.

## 8. Over-Engineered Shared Kernel

**Symptom:** Extracting everything into a SharedKernel or Common folder early on.

```
// ANTI-PATTERN: Everything extracted too early
SharedKernel/
  ProductValidator.cs      // Only used by 2 Product slices
  OrderMappingProfile.cs   // Only relevant to Order feature group
  GenericRepository.cs     # EF Core DbContext is already a repository
  BaseEntity.cs            # Just has Id and CreatedAt
```

**Problem:** Low cohesion in shared code. Changes to shared kernel affect everyone.

**Fix:** Keep shared kernel minimal. Shared code should genuinely be used by 3+ unrelated slices. Feature-local shared folders for entity-group-specific code.

## 9. Synchronous Module Communication

**Symptom:** Module A directly calls Module B's handler or service.

```csharp
// ANTI-PATTERN
public class CreateOrderHandler : IRequestHandler<Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        // ... create order ...
        // Direct call to another module!
        await _inventoryModule.ReserveStock(items);
        // If this fails, order is saved but inventory isn't updated
    }
}
```

**Problem:** Tight coupling, partial failures, hard to extract modules into services later.

**Fix:** Use async events with Outbox Pattern for cross-module communication.

## 10. Ignoring Cross-Cutting Concerns

**Symptom:** Each slice implements its own logging, error handling, authentication checks.

**Problem:** Inconsistent behavior across the app. Security holes. Repeated boilerplate.

**Fix:** Use MediatR pipeline behaviors for validation, logging, metrics. Use middleware for auth and global exception handling. Share infrastructure, not business logic.

## VSA Maturity Checklist

Use this to assess whether your VSA implementation is healthy:

- [ ] Adding a new feature requires touching only one folder
- [ ] Deleting a feature means deleting one folder (no orphaned references)
- [ ] Can change one slice without breaking others
- [ ] Domain entities contain business rules, not just data
- [ ] Handlers are <100 lines (or you know why an exception isn't)
- [ ] No base handler classes or deep inheritance hierarchies
- [ ] Cross-cutting concerns handled by pipeline/middleware, not in handlers
- [ ] Slices don't directly call other slices
- [ ] Shared kernel is small (<10% of codebase)
- [ ] Team can locate any feature in <10 seconds by folder structure
