// Generate a Word document of the train-ticket issue draft.
// Run: NODE_PATH=$(npm root -g) node build_docx.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, LevelFormat,
  HeadingLevel, ShadingType, BorderStyle,
} = require("docx");

const OUT = process.argv[2] || "train-ticket-issue-refresh-disabled-downstream-call.docx";

// ---------- helpers ----------
function codeBlock(lines) {
  // Each line is one paragraph with monospace font + light gray shading.
  return lines.split("\n").map((line) =>
    new Paragraph({
      children: [new TextRun({ text: line.length ? line : " ", font: "Consolas", size: 18 })],
      shading: { type: ShadingType.CLEAR, fill: "F2F2F2" },
      indent: { left: 480, right: 240 },
      spacing: { before: 0, after: 0 },
    })
  );
}

function bodyText(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, ...opts })],
    spacing: { before: 80, after: 120 },
  });
}

function bullet(text, opts = {}) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text, ...opts })],
    spacing: { before: 40, after: 80 },
  });
}

function numbered(items) {
  return items.map((it) =>
    new Paragraph({
      numbering: { reference: "numbers", level: 0 },
      children: [new TextRun({ text: it })],
      spacing: { before: 40, after: 100 },
    })
  );
}

// ---------- content ----------
const children = [];

// Title
children.push(
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun("Issue draft — Disabled downstream call in `queryOrdersForRefresh`")],
  })
);

// Metadata block
children.push(
  bullet("Status: DRAFT — for review before submission. Not yet posted to GitHub."),
  bullet("Target: https://github.com/FudanSELab/train-ticket"),
  bullet("Submission channel: normal issue (repository has no SECURITY.md / CONTRIBUTING.md)."),
  bullet("Expected outcome: low response probability (repo pushed 2025-11-21, 69 open issues with long zero-comment history). Submitted as a correctness/benchmark-integrity report, not with an expectation of a fix.")
);

// Title section
children.push(
  new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Title")] }),
  bodyText("`queryOrdersForRefresh` disables its only downstream call (`queryForStationId`) in both order services, making `ts-order-service -> ts-station-service` fault-injection paths unreachable on the production path")
);

// Summary
children.push(
  new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Summary")] }),
  bodyText("In both `ts-order-service` and `ts-order-other-service`, the only production-path call to the station name-list endpoint is commented out inside `queryOrdersForRefresh`. As a result, orders are returned with raw station UUIDs (`order.from` / `order.to`) instead of station names, and any fault-injection / dependency-failure experiment targeting the `ts-order-service -> ts-station-service` call edge from the `/order/refresh` workflow never exercises the real downstream call."),
  bodyText("The `queryForStationId` method itself is fully implemented and covered by unit tests, but it is no longer reachable from any production request.")
);

// Environment
children.push(
  new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Environment")] }),
  bullet("Repository: FudanSELab/train-ticket"),
  bullet("Branch: master"),
  bullet("Commit inspected: 313886e99befb94be6cd45f085c98e0019f59829 (pinned during analysis)")
);

// Evidence
children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Evidence")] }));

children.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("1. `ts-order-service` — call commented out")] }));
children.push(bodyText("`ts-order-service/src/main/java/order/service/OrderServiceImpl.java:192-206`:"));
children.push(...codeBlock(`public Response queryOrdersForRefresh(OrderInfo qi, String accountId, HttpHeaders headers) {
    ArrayList<Order> orders =   queryOrders(qi, accountId, headers).getData();
    ArrayList<String> stationIds = new ArrayList<>();
    for (Order order : orders) {
        stationIds.add(order.getFrom());
        stationIds.add(order.getTo());
    }

    // List<String> names = queryForStationId(stationIds, headers);   // <-- disabled (line 200)
    for (int i = 0; i < orders.size(); i++) {
        orders.get(i).setFrom(stationIds.get(i * 2));        // stationId (UUID) is returned as-is
        orders.get(i).setTo(stationIds.get(i * 2 + 1));
    }
    return new Response<>(1, "Query Orders For Refresh Success", orders);
}`));
children.push(bodyText("The method it would call is present and implemented (`OrderServiceImpl.java:208-220`):"));
children.push(...codeBlock(`public List<String> queryForStationId(List<String> ids, HttpHeaders headers) {
    HttpEntity requestEntity = new HttpEntity(ids, null);
    String station_service_url = getServiceUrl("ts-station-service");
    ResponseEntity<Response<List<String>>> re = restTemplate.exchange(
            station_service_url + "/api/v1/stationservice/stations/namelist",
            HttpMethod.POST, requestEntity,
            new ParameterizedTypeReference<Response<List<String>>>() {});
    ...
}`));

children.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("2. `ts-order-other-service` — same pattern")] }));
children.push(bodyText("`ts-order-other-service/src/main/java/other/service/OrderOtherServiceImpl.java:209-221`:"));
children.push(...codeBlock(`public Response queryOrdersForRefresh(QueryInfo qi, String accountId, HttpHeaders headers) {
    ArrayList<Order> orders = queryOrders(qi, accountId, headers).getData();
    ArrayList<String> stationIds = new ArrayList<>();
    for (Order order : orders) { stationIds.add(order.getFrom()); stationIds.add(order.getTo()); }
    for (int i = 0; i < orders.size(); i++) {
        orders.get(i).setFrom(stationIds.get(i * 2));
        orders.get(i).setTo(stationIds.get(i * 2 + 1));
    }
    return new Response<>(1, success, orders);
}`));
children.push(bodyText("The call to `queryForStationId` is absent here too; the method itself is implemented at `OrderOtherServiceImpl.java:223-235`."));

children.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("3. Endpoint wiring")] }));
children.push(bullet("`OrderController.java:65` — `@PostMapping(path = \"/order/refresh\")` -> `queryOrdersForRefresh`"));
children.push(bullet("`OrderOtherController.java:71-74` — `/order/refresh` -> `queryOrdersForRefresh`"));

children.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun("4. Unit tests cover the method, not the production path")] }));
children.push(bullet("`ts-order-service/src/test/java/order/service/OrderServiceImplTest.java:191` — calls `queryForStationId` directly with a mocked `RestTemplate` (function-level evidence only)"));
children.push(bullet("Same for `ts-order-other-service/src/test/java/other/service/OrderOtherServiceImplTest.java:192`"));

// Impact
children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Impact")] }));
children.push(...numbered([
  "Benchmark integrity / fault-injection reachability. This benchmark advertises rich service call chains for fault injection. For the `/order/refresh` workflow the real `ts-order-service -> ts-station-service` dependency edge is not executed at all. Chaos/NetworkChaos experiments scoped to that edge from this workflow silently exercise nothing, which can be misread as \"resilience\" when it is actually non-execution.",
  "Response semantics. `order.from` / `order.to` are returned as raw station UUIDs instead of resolved names — a behavior change from what the method name (`Refresh`) and the preserved downstream code imply.",
  "Dead code. `queryForStationId` is maintained, logged, and unit-tested but unreachable from production, so the dependency it models (`ts-station-service /stations/namelist`) is unexercised and untested end-to-end.",
]));

// Reproduction
children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Reproduction")] }));
children.push(...codeBlock(`git clone https://github.com/FudanSELab/train-ticket.git
git checkout 313886e99befb94be6cd45f085c98e0019f59829
# static: grep -rn "queryForStationId" ts-order-service/src/main/java/order/service/OrderServiceImpl.java
#   -> only the commented line 200 in queryOrdersForRefresh
# runtime (isolated lab): POST /api/v1/orderservice/order/refresh with a login that owns orders
#   -> response orders contain station UUIDs in from/to, and no call to
#      /api/v1/stationservice/stations/namelist is observed from ts-order-service`));

// Suggested fix
children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Suggested fix")] }));
children.push(bodyText("Restore the downstream call and handle the empty/failure case explicitly:"));
children.push(...codeBlock(`List<String> names = queryForStationId(stationIds, headers);
// fall back to stationIds when names is null/empty/error, and log the fallback`));
children.push(bodyText("or, if disabling the call is intentional, document it in the README/code comment and mark the dependency edge as non-executable so fault-injection studies do not target it."));

// Notes
children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Notes")] }));
children.push(bullet("Reported for research purposes (fault-injection methodology validation). No credentials or secrets are disclosed."));
children.push(bullet("The repository has no SECURITY.md; this is filed as a normal issue."));
children.push(bullet("Additional context (same finding in the context of the project's own fault-inject-deployment/ scripts): the injected Istio VirtualService/DestinationRule targets described for order workflows will not exercise the station dependency either, as long as this call remains disabled."));

// ---------- document ----------
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUT, buffer);
  console.log("WROTE " + OUT + " (" + buffer.length + " bytes)");
});
