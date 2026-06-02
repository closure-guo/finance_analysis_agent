# Implementation Patterns

## CQRS with Vertical Slices

CQRS emerges naturally in VSA. Each slice is either a **Command** (mutates state) or a **Query** (reads data).

```csharp
// COMMAND slice - CreateProduct.cs
public static class CreateProduct
{
    public record Command(string Name, decimal Price) : IRequest<Result<Guid>>;

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
}

// QUERY slice - GetProduct.cs
public static class GetProduct
{
    public record Query(Guid Id) : IRequest<Result<ProductDto>>;

    public class Handler(AppDbContext db) : IRequestHandler<Query, Result<ProductDto>>
    {
        public async Task<Result<ProductDto>> Handle(Query req, CancellationToken ct)
        {
            var product = await db.Products.FindAsync(req.Id, ct);
            return product == null
                ? Result<ProductDto>.Failure("Product.NotFound", "Product not found")
                : Result<ProductDto>.Success(new ProductDto(product.Id, product.Name, product.Price));
        }
    }
}
```

## REPR Pattern (Request-Endpoint-Response)

REPR defines that each API endpoint has exactly three components:

```csharp
// Features/Products/GetProduct/GetProduct.cs
public static class GetProduct
{
    // Request (Query)
    public record Query(Guid Id) : IRequest<Result<Response>>;

    // Response DTO
    public record Response(Guid Id, string Name, decimal Price);

    // Endpoint definition
    public class Endpoint : IEndpoint
    {
        public void MapEndpoint(IEndpointRouteBuilder app)
        {
            app.MapGet("/api/products/{id:guid}", async (Guid id, IMediator mediator, CancellationToken ct) =>
            {
                var result = await mediator.Send(new Query(id), ct);
                return result.IsSuccess ? Results.Ok(result.Value) : Results.NotFound();
            });
        }
    }

    // Handler
    public class Handler(AppDbContext db) : IRequestHandler<Query, Result<Response>> { ... }
}
```

### Endpoint Definition Options

**Option A: Minimal API inline (simplest)**
```csharp
app.MapGet("/api/products/{id}", async (Guid id, IMediator m, CancellationToken ct) =>
    await m.Send(new GetProduct.Query(id), ct));
```

**Option B: Carter module**
```csharp
public class GetProductEndpoint : ICarterModule
{
    public void AddRoutes(IEndpointRouteBuilder app) =>
        app.MapGet("/api/products/{id}", async (Guid id, IMediator m, CancellationToken ct) => ...);
}
```

**Option C: FastEndpoints**
```csharp
public class GetProductEndpoint : Endpoint<GetProduct.Query, GetProduct.Response>
{
    public override void Configure() => Get("/api/products/{Id}");
    public override async Task HandleAsync(GetProduct.Query q, CancellationToken ct) => ...
}
```

## MediatR Pipeline Behaviors

Handle cross-cutting concerns at the infrastructure level, not in slices:

```csharp
// Validation Pipeline
public class ValidationBehavior<TRequest, TResponse>(IEnumerable<IValidator<TRequest>> validators)
    : IPipelineBehavior<TRequest, TResponse> where TRequest : notnull
{
    public async Task<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken ct)
    {
        if (!validators.Any()) return await next();

        var context = new ValidationContext<TRequest>(request);
        var results = await Task.WhenAll(validators.Select(v => v.ValidateAsync(context, ct)));
        var failures = results.SelectMany(r => r.Errors).Where(f => f != null).ToList();

        if (failures.Any()) throw new ValidationException(failures);
        return await next();
    }
}

// Logging Pipeline
public class LoggingBehavior<TRequest, TResponse>(ILogger<TRequest> logger)
    : IPipelineBehavior<TRequest, TResponse> where TRequest : notnull
{
    public async Task<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken ct)
    {
        logger.LogInformation("Handling {RequestType}", typeof(TRequest).Name);
        var response = await next();
        logger.LogInformation("Handled {RequestType}", typeof(TRequest).Name);
        return response;
    }
}
```

Registration:
```csharp
builder.Services.AddMediatR(cfg =>
{
    cfg.RegisterServicesFromAssembly(typeof(Program).Assembly);
    cfg.AddOpenBehavior(typeof(ValidationBehavior<,>));
    cfg.AddOpenBehavior(typeof(LoggingBehavior<,>));
});
```

## DDD Integration

Push complex business logic into the domain model:

```csharp
// Domain entity with rich behavior
public class Order
{
    private readonly List<OrderItem> _items = new();

    public Guid Id { get; private set; }
    public OrderStatus Status { get; private set; }
    public IReadOnlyList<OrderItem> Items => _items.AsReadOnly();

    public static Order Create(Guid customerId) => new() { Id = Guid.NewGuid(), Status = OrderStatus.Pending };

    public Result AddItem(Product product, int quantity)
    {
        if (Status != OrderStatus.Pending)
            return Result.Failure("Order.AlreadySubmitted", "Cannot modify submitted order");

        if (quantity <= 0)
            return Result.Failure("Order.InvalidQuantity", "Quantity must be positive");

        _items.Add(new OrderItem(product.Id, product.Price, quantity));
        return Result.Success();
    }

    public Result Submit()
    {
        if (!_items.Any())
            return Result.Failure("Order.Empty", "Cannot submit empty order");

        Status = OrderStatus.Submitted;
        return Result.Success();
    }
}
```

Then in the slice handler:
```csharp
public class Handler(AppDbContext db) : IRequestHandler<SubmitOrder.Command, Result>
{
    public async Task<Result> Handle(Command req, CancellationToken ct)
    {
        var order = await db.Orders.Include(o => o.Items).FirstAsync(o => o.Id == req.OrderId, ct);
        var result = order.Submit();  // domain logic, not in handler
        if (result.IsFailure) return result;

        await db.SaveChangesAsync(ct);
        return Result.Success();
    }
}
```

## Validation with FluentValidation

Per-slice validators, auto-discovered by the pipeline:

```csharp
public static class CreateProduct
{
    public record Command(string Name, decimal Price) : IRequest<Result<Guid>>;

    public class Validator : AbstractValidator<Command>
    {
        public Validator()
        {
            RuleFor(x => x.Name).NotEmpty().MaximumLength(200);
            RuleFor(x => x.Price).GreaterThan(0);
        }
    }
    // ... handler
}
```

## Result Pattern

Standardize operation outcomes without exceptions:

```csharp
public class Result
{
    public bool IsSuccess { get; }
    public bool IsFailure => !IsSuccess;
    public Error Error { get; }

    private Result(bool isSuccess, Error error) { ... }

    public static Result Success() => new(true, Error.None);
    public static Result Failure(string code, string message) => new(false, new Error(code, message));
}

public class Result<T> : Result
{
    public T Value { get; }
    private Result(T value) : base(true, Error.None) => Value = value;
    public static Result<T> Success(T value) => new(value);
    public new static Result<T> Failure(string code, string message) => new(false, new Error(code, message));
}
```

## Auto-Endpoint Discovery

Register all endpoints automatically to avoid manual wiring in Program.cs:

```csharp
// Marker interface
public interface IEndpoint
{
    void MapEndpoint(IEndpointRouteBuilder app);
}

// Auto-registration extension
public static class EndpointExtensions
{
    public static IEndpointRouteBuilder MapEndpoints(this IEndpointRouteBuilder app, Assembly assembly)
    {
        var endpoints = assembly.GetTypes()
            .Where(t => typeof(IEndpoint).IsAssignableFrom(t) && !t.IsAbstract)
            .Select(Activator.CreateInstance)
            .Cast<IEndpoint>();

        foreach (var endpoint in endpoints)
            endpoint.MapEndpoint(app);

        return app;
    }
}

// In Program.cs
app.MapEndpoints(typeof(Program).Assembly);
```

## Query Optimization Strategies

Queries can be optimized independently per slice:

```csharp
// Slice 1: Simple EF Core query
public class Handler(AppDbContext db) : IRequestHandler<Query, Result<List<ProductDto>>>
{
    public async Task<Result<List<ProductDto>>> Handle(Query req, CancellationToken ct)
    {
        var products = await db.Products
            .Where(p => p.IsActive)
            .Select(p => new ProductDto(p.Id, p.Name, p.Price))
            .ToListAsync(ct);
        return Result<List<ProductDto>>.Success(products);
    }
}

// Slice 2: Complex query with raw SQL/Dapper for performance
public class Handler(IDbConnection db) : IRequestHandler<Query, Result<DashboardDto>>
{
    public async Task<Result<DashboardDto>> Handle(Query req, CancellationToken ct)
    {
        var sql = "SELECT ... FROM ... COMPLEX JOIN ...";
        var data = await db.QueryAsync<DashboardDto>(sql, new { req.UserId });
        return Result<DashboardDto>.Success(data.First());
    }
}

// Slice 3: ProjectTo with AutoMapper for simple mappings
public class Handler(AppDbContext db, IMapper mapper) : IRequestHandler<Query, Result<List<ProductDto>>>
{
    public async Task<Result<List<ProductDto>>> Handle(Query req, CancellationToken ct)
    {
        var products = await db.Products
            .Where(p => p.CategoryId == req.CategoryId)
            .ProjectTo<ProductDto>(mapper.ConfigurationProvider)
            .ToListAsync(ct);
        return Result<List<ProductDto>>.Success(products);
    }
}
```
