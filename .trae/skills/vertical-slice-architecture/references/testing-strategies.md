# Testing Strategies for VSA

## Philosophy

VSA makes testing straightforward because each slice is self-contained. Test the handler as the unit of work.

## Unit Testing Handlers

Test handlers directly without mocking the database. Use in-memory DB or mock only external services.

```csharp
public class CreateProductHandlerTests
{
    private readonly AppDbContext _db;
    private readonly CreateProduct.Handler _handler;

    public CreateProductHandlerTests()
    {
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString())
            .Options;
        _db = new AppDbContext(options);
        _handler = new CreateProduct.Handler(_db);
    }

    [Fact]
    public async Task Handle_WithValidRequest_CreatesProduct()
    {
        var command = new CreateProduct.Command("Test Product", 99.99m);
        var result = await _handler.Handle(command, CancellationToken.None);

        Assert.True(result.IsSuccess);
        Assert.NotEqual(Guid.Empty, result.Value);

        var product = await _db.Products.FindAsync(result.Value);
        Assert.NotNull(product);
        Assert.Equal("Test Product", product.Name);
    }

    [Fact]
    public async Task Handle_WithDuplicateName_ReturnsFailure()
    {
        _db.Products.Add(new Product("Existing", 10m));
        await _db.SaveChangesAsync();

        var command = new CreateProduct.Command("Existing", 99.99m);
        var result = await _handler.Handle(command, CancellationToken.None);

        Assert.True(result.IsFailure);
        Assert.Equal("Product.DuplicateName", result.Error.Code);
    }
}
```

## Integration Testing

Test the full request pipeline: endpoint -> mediator -> handler -> database.

```csharp
public class ProductApiTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;
    private readonly WebApplicationFactory<Program> _factory;

    public ProductApiTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory.WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                // Replace with test container DB
                services.RemoveAll<DbContextOptions<AppDbContext>>();
                services.AddDbContext<AppDbContext>(options =>
                    options.UseNpgsql(_postgresContainer.GetConnectionString()));
            });
        });
        _client = _factory.CreateClient();
    }

    [Fact]
    public async Task CreateProduct_Returns201WithId()
    {
        var request = new { Name = "Integration Test", Price = 49.99m };
        var response = await _client.PostAsJsonAsync("/api/products", request);

        response.StatusCode.Should().Be(HttpStatusCode.Created);
        var result = await response.Content.ReadFromJsonAsync<CreateProduct.Response>();
        result!.Id.Should().NotBeEmpty();
    }
}
```

### Integration Test Infrastructure (Recommended Stack)

- **TestContainers**: Real PostgreSQL/SQL Server in Docker per test run
- **Respawn**: Fast database reset between tests (at unit test speed)
- **No in-memory database**: Test against real DB for realistic behavior

```csharp
public class IntegrationTestBase : IAsyncLifetime
{
    private readonly PostgreSqlContainer _postgres = new PostgreSqlBuilder().Build();
    private DbContextOptions<AppDbContext> _dbOptions = null!;
    private Respawner _respawner = null!;

    public async Task InitializeAsync()
    {
        await _postgres.StartAsync();
        _dbOptions = new DbContextOptionsBuilder<AppDbContext>()
            .UseNpgsql(_postgres.GetConnectionString())
            .Options;

        await using var db = new AppDbContext(_dbOptions);
        await db.Database.MigrateAsync();

        _respawner = await Respawner.CreateAsync(
            _postgres.GetConnectionString(),
            new RespawnerOptions { DbAdapter = DbAdapter.Postgres });
    }

    public async Task DisposeAsync() => await _postgres.DisposeAsync();

    protected async Task ResetDatabaseAsync() =>
        await _respawner.ResetAsync(_postgres.GetConnectionString());

    protected AppDbContext CreateDbContext() => new(_dbOptions);
}
```

## Architecture Testing

Use NetArchTest to enforce architectural rules automatically:

```csharp
public class ArchitectureTests
{
    private readonly Assembly _assembly = typeof(Program).Assembly;

    [Fact]
    public void Handlers_Should_ResideInFeaturesFolder()
    {
        var result = Types.InAssembly(_assembly)
            .That().Inherit(typeof(IRequestHandler<,>))
            .Should().ResideInNamespace("Application.Features")
            .GetResult();

        result.IsSuccessful.Should().BeTrue();
    }

    [Fact]
    public void Features_Should_Not_DependOnEachOther()
    {
        // Each feature namespace should not reference other feature namespaces
        var featureTypes = Types.InAssembly(_assembly)
            .That().ResideInNamespaceStartingWith("Application.Features.");

        var featureNamespaces = featureTypes.GetTypes()
            .Select(t => t.Namespace!.Split('.').Take(3).Aggregate((a, b) => $"{a}.{b}"))
            .Distinct()
            .ToList();

        foreach (var ns in featureNamespaces)
        {
            var otherFeatures = featureNamespaces.Where(f => f != ns);
            var result = Types.InAssembly(_assembly)
                .That().ResideInNamespace(ns)
                .ShouldNot().DependOnAny(otherFeatures.Select(f =>
                    Types.InAssembly(_assembly).That().ResideInNamespaceStartingWith(f + ".")))
                .GetResult();

            result.IsSuccessful.Should().BeTrue($"Feature {ns} should not depend on other features");
        }
    }

    [Fact]
    public void Domain_Entities_Should_Not_DependOnInfrastructure()
    {
        var result = Types.InAssembly(_assembly)
            .That().ResideInNamespace("Domain")
            .ShouldNot().DependOnAny(Types.InAssembly(_assembly)
                .That().ResideInNamespace("Infrastructure"))
            .GetResult();

        result.IsSuccessful.Should().BeTrue();
    }
}
```

## Test Categories

| Test Type | Scope | Speed | Count |
|-----------|-------|-------|-------|
| Unit (Handler) | Single handler, in-memory DB | <50ms | Many (70%+) |
| Integration (API) | Full HTTP request, real DB | <500ms | Medium (20%) |
| Architecture | Code structure rules | <5s | Few (10) |
| E2E | Full browser/UI flow | >1s | Very few |

## Testing Tips

1. **Test handlers, not endpoints**: Endpoint wiring is framework code, test handlers for business logic
2. **Use real Result<T> in assertions**: `result.IsFailure.Should().BeTrue()` instead of checking exceptions
3. **Seed test data per test**: Each test creates its own data, tests are independent
4. **Test the happy path + 2-3 edge cases per handler**: Don't over-test
5. **Test validation separately**: FluentValidation validators can be unit tested in isolation

```csharp
public class CreateProductValidatorTests
{
    private readonly CreateProduct.Validator _validator = new();

    [Fact]
    public void Name_Empty_ShouldFail()
    {
        var result = _validator.TestValidate(new CreateProduct.Command("", 10m));
        result.ShouldHaveValidationErrorFor(x => x.Name);
    }
}
```
