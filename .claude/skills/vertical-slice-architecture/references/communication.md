# Cross-Slice Communication & Event-Driven Integration

## Core Rule

Slices should **not directly call each other**. Each slice queries the database directly for data it needs. When slices need to communicate, use events.

## Why No Direct Calls?

```csharp
// BAD: Slice A calls Slice B -> tight coupling, distributed transaction risk
public class CreateOrderHandler : IRequestHandler<CreateOrder.Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        // ... create order ...
        await _mediator.Send(new ReserveStock.Command(...)); // DON'T DO THIS
    }
}
```

Direct synchronous calls between slices:
- Create hidden coupling (changing Slice B breaks Slice A)
- Risk distributed transactions
- Violate slice autonomy

## Communication Patterns

### Pattern 1: Domain Events (In-Process, Same Bounded Context)

For communication between slices within the same bounded context/module:

```csharp
// Slice 1: Publish domain event
public static class CreateOrder
{
    public class Handler(AppDbContext db, IPublisher publisher) : IRequestHandler<Command, Result>
    {
        public async Task<Result> Handle(Command req, CancellationToken ct)
        {
            var order = Order.Create(req.CustomerId);
            // ... add items ...
            db.Orders.Add(order);

            // Publish domain event
            await publisher.Publish(new OrderCreatedEvent(order.Id, order.Items), ct);

            await db.SaveChangesAsync(ct);
            return Result.Success();
        }
    }
}

// Slice 2: Handle the event
public class ReserveStockHandler(AppDbContext db) : INotificationHandler<OrderCreatedEvent>
{
    public async Task Handle(OrderCreatedEvent notification, CancellationToken ct)
    {
        foreach (var item in notification.Items)
        {
            var product = await db.Products.FindAsync(item.ProductId, ct);
            product.ReserveStock(item.Quantity);
        }
        await db.SaveChangesAsync(ct);
    }
}
```

Domain events:
- Published and handled **in-process** via MediatR notifications
- Part of the same transaction (SaveChanges saves both order and stock reservations)
- Use for closely related operations within same bounded context

### Pattern 2: Integration Events (Across Bounded Contexts)

For communication between separate modules/bounded contexts:

```csharp
// Module: Ordering
public class OrderCreatedIntegrationEvent
{
    public Guid OrderId { get; }
    public Guid CustomerId { get; }
    public List<OrderItem> Items { get; }
    public DateTime OccurredOn { get; } = DateTime.UtcNow;
}

// Published via message broker (RabbitMQ, MassTransit, etc.)
public class CreateOrderHandler(AppDbContext db, IEventBus bus) : IRequestHandler<...>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        // ... create order ...
        await db.SaveChangesAsync(ct);

        // Publish integration event (async, out-of-process)
        await bus.PublishAsync(new OrderCreatedIntegrationEvent(order.Id, ...));
        return Result.Success();
    }
}

// Module: Inventory (separate, processes event asynchronously)
public class OrderCreatedHandler(ILogger<OrderCreatedHandler> logger) : IConsumer<OrderCreatedIntegrationEvent>
{
    public async Task Consume(ConsumeContext<OrderCreatedIntegrationEvent> context)
    {
        // Update inventory independently
        logger.LogInformation("Updating inventory for order {OrderId}", context.Message.OrderId);
        // ...
    }
}
```

Integration events:
- **Asynchronous and out-of-process**
- Use message broker (RabbitMQ, Kafka, Azure Service Bus)
- Implement Outbox Pattern for reliable delivery
- Separate transactions in each module

### Pattern 3: Public API / Facade (Synchronous, Controlled)

When one module needs to synchronously query another:

```csharp
// Module A exposes a public API (internal to the monolith)
public interface ICatalogModuleApi
{
    Task<ProductDto?> GetProductAsync(Guid productId, CancellationToken ct = default);
    Task<bool> ProductExistsAsync(Guid productId, CancellationToken ct = default);
}

internal class CatalogModuleApi(AppDbContext db) : ICatalogModuleApi { ... }

// Module B uses it via DI
public class CreateOrderHandler(
    AppDbContext db,
    ICatalogModuleApi catalog,  // injected, not direct DB access
    ILogger<CreateOrderHandler> logger
) : IRequestHandler<Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        // Validate products exist via catalog module's API
        foreach (var item in req.Items)
        {
            if (!await catalog.ProductExistsAsync(item.ProductId, ct))
                return Result.Failure("Order.InvalidProduct", $"Product {item.ProductId} not found");
        }
        // ... rest of handler
    }
}
```

Rules for module APIs:
- Expose **query-only** operations (no commands)
- Return **DTOs**, not domain entities
- Keep interfaces in `SharedKernel`, implementations internal
- Each module registers its public API in DI

### Pattern 4: Database Integration (Read-Only, Reporting)

For reporting/queries that span modules:

```csharp
// Direct read from another module's tables (read-only!)
public class Handler(AppDbContext db) : IRequestHandler<Query, Result<List<OrderSummaryDto>>>
{
    public async Task<Result<List<OrderSummaryDto>>> Handle(Query req, CancellationToken ct)
    {
        var orders = await db.Orders
            .Join(db.Products, o => o.ProductId, p => p.Id, (o, p) => new { o, p })
            .Join(db.Customers, x => x.o.CustomerId, c => c.Id, (x, c) => new OrderSummaryDto {
                OrderId = x.o.Id,
                ProductName = x.p.Name,
                CustomerName = c.Name,
                ...
            })
            .ToListAsync(ct);
        return Result<List<OrderSummaryDto>>.Success(orders);
    }
}
```

**Warning:** Read-only cross-module queries are acceptable in monoliths. For writes, always use events.

## Event Publishing Approaches

### Approach A: Immediate (Simplest)

```csharp
await db.SaveChangesAsync(ct);
await mediator.Publish(new OrderCreatedEvent(order.Id, ...), ct);
```

Risk: If event handler fails, data is already saved.

### Approach B: Pre-Save (Transactional)

```csharp
// Collect events in entity
typepublic class Order : Entity
{
    private List<DomainEvent> _domainEvents = new();
    public IReadOnlyCollection<DomainEvent> DomainEvents => _domainEvents.AsReadOnly();

    public void AddItem(Product product, int qty)
    {
        // ... add item ...
        _domainEvents.Add(new OrderItemAddedEvent(Id, product.Id, qty));
    }
}

// Override SaveChanges to dispatch after save
public override async Task<int> SaveChangesAsync(CancellationToken ct = default)
{
    var entities = ChangeTracker.Entries<Entity>()
        .Where(e => e.Entity.DomainEvents.Any())
        .Select(e => e.Entity);

    var result = await base.SaveChangesAsync(ct);

    foreach (var entity in entities)
    {
        foreach (var evt in entity.DomainEvents)
            await _mediator.Publish(evt, ct);
        entity.ClearDomainEvents();
    }

    return result;
}
```

### Approach C: Outbox Pattern (Production-Grade)

For reliable delivery across modules:

```csharp
// 1. Store event in Outbox table (same transaction as business data)
public class CreateOrderHandler(AppDbContext db) : IRequestHandler<Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        var order = Order.Create(req.CustomerId);
        db.Orders.Add(order);
        db.OutboxMessages.Add(new OutboxMessage {
            Type = nameof(OrderCreatedIntegrationEvent),
            Payload = JsonSerializer.Serialize(new OrderCreatedIntegrationEvent(order.Id, ...)),
            OccurredOn = DateTime.UtcNow
        });
        await db.SaveChangesAsync(ct); // Both saved in one transaction
        return Result.Success();
    }
}

// 2. Background worker polls and publishes
public class OutboxProcessor(AppDbContext db, IEventBus bus) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var messages = await db.OutboxMessages
                .Where(m => !m.Processed)
                .OrderBy(m => m.OccurredOn)
                .Take(10)
                .ToListAsync(stoppingToken);

            foreach (var message in messages)
            {
                try
                {
                    var evt = Deserialize(message);
                    await bus.PublishAsync(evt, stoppingToken);
                    message.Processed = true;
                    message.ProcessedOn = DateTime.UtcNow;
                }
                catch { /* retry later */ }
            }
            await db.SaveChangesAsync(stoppingToken);
            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }
}
```

## Communication Pattern Selection Guide

| Scenario | Pattern | Mechanism |
|----------|---------|-----------|
| Same module, closely related | Domain Events | MediatR INotificationHandler |
| Same module, loosely related | Domain Events | MediatR INotificationHandler |
| Different modules, async acceptable | Integration Events | Message broker + Outbox |
| Different modules, sync required | Public API | Internal interface/DI |
| Cross-module reporting | DB Read | Direct read-only queries |
