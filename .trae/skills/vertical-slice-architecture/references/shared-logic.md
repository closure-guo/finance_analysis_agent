# Shared Logic & Code Reuse in VSA

## The Core Philosophy: WET before DRY

In VSA, controlled duplication is preferable to premature abstraction. The goal is **slice independence**, not zero duplication.

> "DRY is about duplicated knowledge, not duplicated code. If two pieces of code change for different reasons, keep them separate."

**Decision Framework:**
- Write code twice in two different slices -- fine, wait for the pattern to emerge
- Same code in three or more slices -- consider extraction
- Extract only when the **reason to change** is truly identical

## The Rule of Three

```
2 slices with similar code     -> Keep duplicated (might diverge)
3+ slices with identical code  -> Time to extract
Shared code changes for different business reasons -> Keep separate
```

Real example: `ProcessPayment` and `RefundPayment` both validate positive amounts. Three months later, refunds need negative amounts. If shared, you'd add conditional logic. If duplicated, you simply change one slice.

## What to Share vs What to Duplicate

| Share (infrastructure) | Duplicate per slice (business logic) |
|------------------------|--------------------------------------|
| Logging, telemetry | Validation rules (if business-specific) |
| Authentication/Authorization | Query logic (selects what the slice needs) |
| Email sender, blob storage, PDF renderer | Business workflows (CreateInvoice, ProcessOrder) |
| Database connection, caching | Response DTOs (each slice returns what it needs) |
| Clock, IdGenerator, pagination | Mapping logic (if slice-specific) |
| Result<T>, Error types | API endpoint wiring |
| Exception handling middleware | Domain events publishing |

## Extraction Strategies

### 1. Push Logic into Domain Model (Preferred for Business Rules)

Share business rules through entities, value objects, domain services:

```csharp
// Domain/Shipments/Shipment.cs
public sealed class Shipment
{
    public ShipmentStatus Status { get; private set; }

    public bool CanBeCancelled() =>
        Status is ShipmentStatus.Pending or ShipmentStatus.Confirmed;

    public bool CanBeShipped() =>
        Status == ShipmentStatus.Confirmed;

    public Result Cancel() { ... }
    public Result Dispatch() { ... }
}
```

Both `CancelShipment` and `GetShipment` slices use `Shipment.CanBeCancelled()` -- shared via domain, not via application service.

### 2. Extract Capabilities, Not Workflows

**Capabilities** (share): Technical building blocks with stable interfaces
- `IEmailSender`, `IBlobStorage`, `IPaymentGateway`
- `ICurrentUserService`, `IDateTimeProvider`

**Workflows** (keep in slices): Business-specific processes that change frequently
- `CreateInvoice`, `ProcessOrder`, `GenerateReport`

```csharp
// Shared capability
public interface IEmailSender
{
    Task SendAsync(string to, string subject, string body, CancellationToken ct = default);
}

// Used within a slice workflow
public class CreateOrderHandler(AppDbContext db, IEmailSender email) : IRequestHandler<...>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        // ... create order logic ...
        await email.SendAsync(order.CustomerEmail, "Order Confirmation", ...);
        return Result.Success();
    }
}
```

### 3. Query Extensions (for Data Access)

For repeated query patterns, use extension methods:

```csharp
// Shared in entity feature folder
public static class OrderQueryExtensions
{
    public static IQueryable<Order> WhereActive(this IQueryable<Order> query) =>
        query.Where(o => o.Status != OrderStatus.Cancelled && !o.IsDeleted);

    public static IQueryable<Order> ByCustomer(this IQueryable<Order> query, Guid customerId) =>
        query.Where(o => o.CustomerId == customerId);
}

// Used in slices
public class Handler(AppDbContext db) : IRequestHandler<Query, Result<List<OrderDto>>>
{
    public async Task<Result<List<OrderDto>>> Handle(Query req, CancellationToken ct)
    {
        var orders = await db.Orders
            .WhereActive()
            .ByCustomer(req.CustomerId)
            .OrderByDescending(o => o.CreatedAt)
            .Select(o => new OrderDto(...))
            .ToListAsync(ct);
        return Result<List<OrderDto>>.Success(orders);
    }
}
```

### 4. Specification Pattern

For complex, reusable query criteria:

```csharp
public class ExpensiveOrdersSpecification : Specification<Order>
{
    public ExpensiveOrdersSpecification(Guid userId)
    {
        AddFilteringQuery(order => order.UserId == userId);
        AddOrderByDescendingQuery(order => order.TotalAmount.Amount);
    }
}
```

### 5. Composition over Inheritance

Never use base handler classes to share code:

```csharp
// BAD: Creates hidden coupling
public abstract class BaseHandler<TRequest, TResponse> { ... }
public class CreateShipmentHandler : BaseHandler<...> { ... }

// GOOD: Use composition
public class CreateShipmentHandler(
    AppDbContext db,
    IEmailSender email,      // composed capability
    ILogger<CreateShipmentHandler> logger  // composed capability
) : IRequestHandler<...> { ... }
```

### 6. Feature-Local Shared Folder

For logic shared only within a domain/feature group:

```
Features/
  Orders/
    Shared/
      OrderItemValidator.cs    # shared by Create and Update
      OrderMappings.cs         # shared mapping logic
    CreateOrder/
      CreateOrder.cs
    UpdateOrder/
      UpdateOrder.cs
```

### 7. Global Shared / Common Folder

For truly cross-cutting types:

```
Application/
  Common/
    Behaviours/                # MediatR pipelines
    Models/
      Result.cs                # Result<T> pattern
      PagedList.cs             # Pagination wrapper
      Error.cs                 # Error type
```

## Repository Decision Tree

With EF Core, you typically **don't need repositories** in VSA:

```
Simple CRUD (FindAsync, Add, SaveChanges)
  -> Use DbContext directly in handler

Slightly complex query (Where, Include, Select)
  -> Use extension methods on IQueryable

Complex query used by 3+ slices (joins, aggregates)
  -> Use Specification pattern or Repository

Raw SQL/Dapper for performance
  -> Extract a query class or use repository
```

Each slice should **query the database directly** for data it needs, not call other slices.

## Folder Placement Guide

When you decide to extract shared code:

| Scope | Placement |
|-------|-----------|
| Used by 2-3 slices of same entity | `Features/EntityName/Shared/` |
| Used by many slices of one bounded context | `Features/Shared/` or `Common/` |
| Used across bounded contexts | `SharedKernel/` |
| Infrastructure/technical | `Infrastructure/` |
