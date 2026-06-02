# VSA Folder Structure & Organization Patterns

## The North Star

Jimmy Bogard's rule: take all code related to a single user request -- from UI to database -- and move it to a single location on disk.

## Four Organization Approaches

### Approach 1: Feature-Based Folders (Multi-File)

Each slice gets its own folder with separate files for each concern.

```
Features/
  CreateShipment/
    CreateShipmentCommand.cs
    CreateShipmentHandler.cs
    CreateShipmentEndpoint.cs
    CreateShipmentValidator.cs
    CreateShipmentResponse.cs
  GetShipmentByNumber/
    GetShipmentByNumberQuery.cs
    GetShipmentByNumberHandler.cs
    GetShipmentByNumberEndpoint.cs
    GetShipmentByNumberResponse.cs
```

**Best for:** Large teams, complex features with lots of logic
**Avoid when:** Simple CRUD, small teams, fast iteration needed

### Approach 2: Single File per Slice (Nested Classes)

Each slice is one file using a static class with nested types.

```
Features/
  CreateShipment.cs      // static class containing Command, Handler, Endpoint, Validator
  GetShipmentByNumber.cs // static class containing Query, Handler, Endpoint, Response
```

```csharp
public static class CreateShipment
{
    public record Command(string OrderId, Address Address) : IRequest<Result<Guid>>;
    public class Handler(AppDbContext db) : IRequestHandler<Command, Result<Guid>> { ... }
    public class Validator : AbstractValidator<Command> { ... }
    public class Endpoint : IEndpoint { ... } // or Carter module
}
```

**Best for:** Small-medium teams, CRUD-heavy apps, maximum navigation speed
**Avoid when:** Very complex features (300+ lines per file)

### Approach 3: Hybrid (Recommended for Most Projects)

Single file for main code, extract cross-cutting concerns (validation, mapping) into separate files.

```
Features/
  CreateShipment/
    CreateShipment.cs           // Command + Handler + Endpoint
    CreateShipment.Validator.cs // extracted validation rules
    CreateShipment.Mapping.cs   // extracted mapping logic
```

**Best for:** Most real-world projects -- balances ceremony with organization

### Approach 4: Pragmatic (Small Solutions / Microservices)

Embed all logic directly in the endpoint, bypass MediatR for truly simple cases.

```csharp
app.MapPost("/api/shipments", async (CreateRequest req, AppDbContext db) => {
    // validation + logic + data access inline
});
```

**Best for:** Small services, prototypes, true CRUD
**Avoid when:** Cross-cutting concerns need central management, complex business logic

## Recommended: Domain-Organized Top Level

For modular monoliths and multi-team setups, organize by domain area at the top level, then use single-file slices within.

```
src/
├── Api/
│   └── Program.cs                    # entry point, DI registration
│
├── Application/                      # all features
│   ├── Scheduling/                   # domain area (team boundary)
│   │   ├── BookAppointment.cs
│   │   ├── CancelAppointment.cs
│   │   ├── GetAppointmentById.cs
│   │   └── AppointmentDto.cs         # shared DTOs within domain
│   │
│   ├── Billing/
│   │   ├── CreateInvoice.cs
│   │   ├── ProcessPayment.cs
│   │   └── InvoiceDto.cs
│   │
│   ├── Domain/                       # shared domain model
│   │   ├── Appointment.cs
│   │   ├── Invoice.cs
│   │   └── Order.cs
│   │
│   └── Common/                       # cross-cutting in application layer
│       ├── Behaviours/               # MediatR pipeline behaviors
│       │   ├── ValidationBehaviour.cs
│       │   └── LoggingBehaviour.cs
│       └── Models/
│           ├── Result.cs
│           └── PagedList.cs
│
└── Infrastructure/
    ├── Persistence/
    │   └── AppDbContext.cs
    ├── EmailSender.cs
    └── BlobStorage.cs
```

**Why this structure:**
- Domain-organized top level = "screaming architecture" -- folder tree shows what the system does
- Single-file slices within = minimal ceremony, high development speed
- `Domain/` for genuinely shared entities (used by multiple slices)
- `Common/` for genuinely shared infrastructure (behaviors, result types)

## Multi-Module / Bounded Context Organization

For large systems with clearly separated bounded contexts:

```
src/
├── Modules/
│   ├── Catalog/                      # bounded context
│   │   ├── Features/
│   │   ├── Domain/
│   │   └── Infrastructure/
│   ├── Basket/                       # bounded context
│   │   ├── Features/
│   │   ├── Domain/
│   │   └── Infrastructure/
│   └── Ordering/
│       ├── Features/
│       ├── Domain/
│       └── Infrastructure/
├── SharedKernel/                     # truly shared across modules
│   ├── Domain/
│   └── Infrastructure/
└── Api/
    └── Program.cs
```

Each module:
- Has its own Features/ folder with vertical slices
- Owns its domain model
- Can only reference SharedKernel (not other modules directly)
- Communicates with other modules via integration events

## Key Rules

1. **One folder per feature/use case** -- never mix unrelated features
2. **No deep nesting** -- 2-3 levels max within a feature folder
3. **Keep files that change together, close together** (Common Closure Principle)
4. **Shared kernel is minimal** -- resist the urge to extract early
5. **Evolve the structure** -- start simple, add organization as domain boundaries clarify
