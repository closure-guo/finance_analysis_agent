---
name: vertical-slice-architecture
description: >
  Vertical Slice Architecture (VSA) best practices for building software organized by
  features/use cases rather than technical layers. Provides guidance on folder structure,
  CQRS implementation with MediatR, REPR pattern, cross-slice communication via domain events,
  shared logic extraction strategies, testing approaches, anti-pattern avoidance, and
  AI agent-specific development workflows.
  Use when: (1) designing or refactoring backend architecture to feature-based organization,
  (2) implementing CQRS with command/query handlers, (3) deciding between VSA and Clean
  Architecture or combining both, (4) structuring .NET/Java/Node.js projects with vertical
  slices, (5) handling cross-cutting concerns (validation, logging, auth) in VSA,
  (6) communicating between slices or bounded contexts, (7) testing handler-based
  architectures, (8) reviewing architecture for VSA anti-patterns,
  (9) AI agents developing software with vertical slice patterns,
  (10) multi-agent parallel development with slice ownership.
---

# Vertical Slice Architecture

Organize code by feature/use case, not by technical layer. Each "slice" is a self-contained unit that encapsulates all code needed for a specific request, from the API endpoint to data access.

## Core Principles

1. **Couple vertically along the axis of change** -- all code for a feature lives together
2. **Minimize coupling between slices, maximize coupling within a slice**
3. **New features only add code** -- no modification of shared code, no side effect anxiety
4. **Each slice chooses its own implementation** -- one uses EF Core, another raw SQL
5. **Start simple (Transaction Script), refactor when code smells appear**

## Quick Start Workflow

### 1. Understand the Feature

Identify the use case. Is it a **Command** (mutates state: POST/PUT/DELETE) or a **Query** (reads: GET)? Name the slice after the action: `CreateProduct`, `GetOrderById`, `CancelAppointment`.

### 2. Create the Slice

Choose a folder structure approach based on complexity:

**Simple features** -- single file with nested classes:
```csharp
public static class CreateProduct
{
    public record Command(string Name, decimal Price) : IRequest<Result<Guid>>;
    public record Response(Guid Id, string Name, decimal Price);

    public class Validator : AbstractValidator<Command>
    {
        public Validator()
        {
            RuleFor(x => x.Name).NotEmpty().MaximumLength(200);
            RuleFor(x => x.Price).GreaterThan(0);
        }
    }

    public class Handler(AppDbContext db) : IRequestHandler<Command, Result<Guid>>
    {
        public async Task<Result<Guid>> Handle(Command req, CancellationToken ct)
        {
            var product = new Product(req.Name, req.Price);
            db.Products.Add(product);
            await db.SaveChangesAsync(ct);
            return Result<Guid>.Success(product.Id);
        }
    }

    public class Endpoint : IEndpoint
    {
        public void MapEndpoint(IEndpointRouteBuilder app)
        {
            app.MapPost("/api/products", async (Command cmd, IMediator m, CancellationToken ct) =>
            {
                var result = await m.Send(cmd, ct);
                return result.IsSuccess ? Results.Ok(result.Value) : Results.BadRequest(result.Error);
            });
        }
    }
}
```

**Complex features** -- folder with extracted files:
```
CreateProduct/
  CreateProduct.cs           # Command + Handler
  CreateProduct.Validator.cs # Validation rules
  CreateProduct.Mapping.cs   # AutoMapper or manual mapping
```

### 3. Register the Endpoint

Auto-discover endpoints at startup:
```csharp
// Program.cs
builder.Services.AddMediatR(cfg => {
    cfg.RegisterServicesFromAssembly(typeof(Program).Assembly);
    cfg.AddOpenBehavior(typeof(ValidationBehavior<,>));
    cfg.AddOpenBehavior(typeof(LoggingBehavior<,>));
});

app.MapEndpoints(typeof(Program).Assembly); // Auto-registers all IEndpoint
```

### 4. Handle Shared Logic (Only When Needed)

Resist the urge to extract early. Follow the **Rule of Three**:
- 2 slices with similar code -> Keep duplicated
- 3+ slices with identical code AND same reason to change -> Extract

Extraction priority:
1. **Push into domain model** (entities, value objects) for business rules
2. **Extract capabilities** (`IEmailSender`, `IBlobStorage`) for technical infrastructure
3. **Use query extensions** (`IQueryable<T>` extension methods) for repeated queries
4. **Create feature-local shared folder** for logic shared within one entity group
5. **Global Common folder** only for truly cross-cutting types (`Result<T>`, pipelines)

### 5. Communicate Between Slices (Avoid Direct Calls)

Slices must not call each other via `_mediator.Send(new OtherSlice.Command(...))`. Use:
- **Domain Events** (MediatR `INotificationHandler`) -- same bounded context, same transaction
- **Integration Events** (message broker + Outbox) -- across bounded contexts, async
- **Public API interfaces** -- cross-module synchronous queries only

### 6. Test the Slice

```csharp
public class CreateProductHandlerTests
{
    [Fact]
    public async Task Handle_WithValidRequest_CreatesProduct()
    {
        var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString()).Options);
        var handler = new CreateProduct.Handler(db);

        var result = await handler.Handle(new CreateProduct.Command("Test", 99.99m), default);

        Assert.True(result.IsSuccess);
        Assert.NotEqual(Guid.Empty, result.Value);
    }
}
```

## Key Decisions

### VSA vs Clean Architecture

| Choose VSA | Choose Clean Architecture | Combine Both |
|-----------|--------------------------|--------------|
| Request-specific logic | Complex domain model | Clean for core domain |
| High velocity, small team | Large enterprise, >5 devs | VSA for peripheral features |
| Microservices/modular monolith | Multiple entry points (API + jobs + handlers) | VSA within bounded contexts |
| Avoid premature abstraction | Long-term stability priority | Hybrid spectrum |

### Folder Structure Selection

| Approach | Best For |
|----------|----------|
| Single file (nested classes) | Small-medium teams, CRUD-heavy |
| Hybrid (main file + extracted concerns) | **Most projects** -- recommended default |
| Feature-based folders | Large teams, complex features |
| Pragmatic (endpoint inline) | Small services, prototypes |

Top-level organization: `Features/DomainArea/ActionName.cs` (e.g., `Features/Billing/CreateInvoice.cs`).

## Cross-Cutting Concerns

Handle at infrastructure level, never in business logic:

```csharp
// Pipeline behavior applies to ALL handlers
public class ValidationBehavior<TRequest, TResponse>(IEnumerable<IValidator<TRequest>> validators)
    : IPipelineBehavior<TRequest, TResponse> where TRequest : notnull
{
    public async Task<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken ct)
    {
        var failures = (await Task.WhenAll(
            validators.Select(v => v.ValidateAsync(request, ct))))
            .SelectMany(r => r.Errors).Where(f => f != null).ToList();

        if (failures.Any()) throw new ValidationException(failures);
        return await next();
    }
}
```

Also use: exception handling middleware, auth middleware/endpoint filters, logging pipelines, feature flags.

## Architecture Health Check

- Adding a feature requires touching **one folder**
- Deleting a feature means **deleting one folder** with no orphans
- Handlers are **<100 lines** (exceptions are deliberate, not accidental)
- **No base handler classes** -- use composition
- **No direct slice-to-slice calls** -- events only
- Shared kernel is **<10% of codebase**
- Domain entities contain **business rules**, not just properties

## References

Load these as needed for detailed guidance:

- **[overview](references/overview.md)** -- Core principles, VSA vs Clean Architecture comparison, when to use, team prerequisites
- **[folder-structure](references/folder-structure.md)** -- 4 folder organization approaches, domain-organized top level, bounded context organization, multi-module setup
- **[implementation-patterns](references/implementation-patterns.md)** -- CQRS implementation, REPR pattern, MediatR pipeline behaviors, DDD integration, validation, Result pattern, auto-endpoint discovery, query optimization
- **[shared-logic](references/shared-logic.md)** -- WET vs DRY philosophy, Rule of Three, what to share vs duplicate, extraction strategies (domain model, capabilities, query extensions), repository decision tree
- **[communication](references/communication.md)** -- Cross-slice communication patterns: domain events, integration events, public APIs, database reads. Event publishing approaches: immediate, pre-save transactional, Outbox Pattern
- **[testing-strategies](references/testing-strategies.md)** -- Handler unit testing, integration testing with TestContainers/Respawn, architecture testing with NetArchTest, test categories, validation testing
- **[anti-patterns](references/anti-patterns.md)** -- 10 common VSA anti-patterns with symptoms, problems, and fixes. Architecture maturity checklist
- **[agent-development](references/agent-development.md)** -- Why VSA fits AI agents, agent-specific workflow, critical rules for agents, common agent mistakes, multi-agent slice ownership patterns
