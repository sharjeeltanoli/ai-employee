import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const ODOO_URL = process.env.ODOO_URL || "http://localhost:8069";
const ODOO_DB = process.env.ODOO_DB || "odoo";
const ODOO_USER = process.env.ODOO_USER || "admin";
const ODOO_PASSWORD = process.env.ODOO_PASSWORD || "admin";

// ─── JSON-RPC helpers ────────────────────────────────────────────────────────

async function jsonRpc(endpoint, method, params) {
  const response = await fetch(`${ODOO_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      method,
      id: Date.now(),
      params,
    }),
  });
  const data = await response.json();
  if (data.error) throw new Error(data.error.data?.message || data.error.message);
  return data.result;
}

async function authenticate() {
  const uid = await jsonRpc("/web/dataset/call_kw", "call", {
    model: "res.users",
    method: "authenticate",
    args: [ODOO_DB, ODOO_USER, ODOO_PASSWORD, {}],
    kwargs: {},
  }).catch(() => null);

  // Fall back to /web/session/authenticate
  if (!uid) {
    const result = await jsonRpc("/web/session/authenticate", "call", {
      db: ODOO_DB,
      login: ODOO_USER,
      password: ODOO_PASSWORD,
    });
    if (!result?.uid) throw new Error("Odoo authentication failed");
    return result.uid;
  }
  return uid;
}

async function callKw(uid, model, method, args = [], kwargs = {}) {
  return jsonRpc("/web/dataset/call_kw", "call", {
    model,
    method,
    args,
    kwargs: {
      context: { lang: "en_US", tz: "UTC", uid },
      ...kwargs,
    },
  });
}

// ─── Server setup ────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "odoo-mcp",
  version: "1.0.0",
});

// ─── Tool: create_customer ───────────────────────────────────────────────────

server.tool(
  "create_customer",
  "Create a new customer (res.partner) in Odoo",
  {
    name: z.string().describe("Customer full name"),
    email: z.string().email().optional().describe("Email address"),
    phone: z.string().optional().describe("Phone number"),
    street: z.string().optional().describe("Street address"),
    city: z.string().optional().describe("City"),
    country_code: z.string().optional().describe("ISO country code, e.g. US"),
  },
  async ({ name, email, phone, street, city, country_code }) => {
    try {
      const uid = await authenticate();

      const vals = { name, customer_rank: 1, is_company: false };
      if (email) vals.email = email;
      if (phone) vals.phone = phone;
      if (street) vals.street = street;
      if (city) vals.city = city;

      if (country_code) {
        const countries = await callKw(uid, "res.country", "search_read", [
          [["code", "=", country_code.toUpperCase()]],
          ["id", "name"],
        ]);
        if (countries.length) vals.country_id = countries[0].id;
      }

      const partnerId = await callKw(uid, "res.partner", "create", [vals]);
      return {
        content: [
          {
            type: "text",
            text: `Customer created successfully.\nID: ${partnerId}\nName: ${name}`,
          },
        ],
      };
    } catch (err) {
      return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
    }
  }
);

// ─── Tool: create_invoice ────────────────────────────────────────────────────

server.tool(
  "create_invoice",
  "Create a customer invoice (account.move) in Odoo",
  {
    customer_name: z.string().describe("Customer name to look up or create"),
    lines: z
      .array(
        z.object({
          description: z.string().describe("Line item description"),
          quantity: z.number().positive().default(1),
          price_unit: z.number().describe("Unit price"),
        })
      )
      .min(1)
      .describe("Invoice line items"),
    currency_code: z.string().optional().default("USD").describe("ISO currency code"),
    invoice_date: z
      .string()
      .optional()
      .describe("Invoice date YYYY-MM-DD (defaults to today)"),
    notes: z.string().optional().describe("Internal notes"),
  },
  async ({ customer_name, lines, currency_code, invoice_date, notes }) => {
    try {
      const uid = await authenticate();

      // Find or create partner
      let partners = await callKw(uid, "res.partner", "search_read", [
        [["name", "ilike", customer_name], ["customer_rank", ">", 0]],
        ["id", "name"],
        0,
        1,
      ]);
      let partnerId;
      if (partners.length) {
        partnerId = partners[0].id;
      } else {
        partnerId = await callKw(uid, "res.partner", "create", [
          { name: customer_name, customer_rank: 1 },
        ]);
      }

      // Resolve currency
      const currencies = await callKw(uid, "res.currency", "search_read", [
        [["name", "=", currency_code.toUpperCase()]],
        ["id", "name"],
        0,
        1,
      ]);
      const currencyId = currencies.length ? currencies[0].id : false;

      // Build invoice lines
      const invoiceLines = lines.map((l) => [
        0,
        0,
        {
          name: l.description,
          quantity: l.quantity,
          price_unit: l.price_unit,
        },
      ]);

      const vals = {
        move_type: "out_invoice",
        partner_id: partnerId,
        invoice_line_ids: invoiceLines,
      };
      if (currencyId) vals.currency_id = currencyId;
      if (invoice_date) vals.invoice_date = invoice_date;
      if (notes) vals.narration = notes;

      const invoiceId = await callKw(uid, "account.move", "create", [vals]);

      // Read back for totals
      const [invoice] = await callKw(uid, "account.move", "read", [
        [invoiceId],
        ["name", "amount_total", "state", "partner_id"],
      ]);

      return {
        content: [
          {
            type: "text",
            text: [
              `Invoice created successfully.`,
              `ID: ${invoiceId}`,
              `Reference: ${invoice.name}`,
              `Customer: ${invoice.partner_id[1]}`,
              `Total: ${invoice.amount_total} ${currency_code.toUpperCase()}`,
              `Status: ${invoice.state}`,
            ].join("\n"),
          },
        ],
      };
    } catch (err) {
      return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
    }
  }
);

// ─── Tool: list_invoices ─────────────────────────────────────────────────────

server.tool(
  "list_invoices",
  "List recent customer invoices from Odoo",
  {
    limit: z.number().int().min(1).max(100).optional().default(20).describe("Max results"),
    state: z
      .enum(["draft", "posted", "cancel", "all"])
      .optional()
      .default("all")
      .describe("Filter by invoice state"),
    customer_name: z.string().optional().describe("Filter by customer name (partial match)"),
  },
  async ({ limit, state, customer_name }) => {
    try {
      const uid = await authenticate();

      const domain = [["move_type", "=", "out_invoice"]];
      if (state !== "all") domain.push(["state", "=", state]);
      if (customer_name) domain.push(["partner_id.name", "ilike", customer_name]);

      const invoices = await callKw(
        uid,
        "account.move",
        "search_read",
        [
          domain,
          ["id", "name", "partner_id", "invoice_date", "amount_total", "state", "currency_id"],
          0,
          limit,
        ],
        { order: "invoice_date desc, id desc" }
      );

      if (!invoices.length) {
        return { content: [{ type: "text", text: "No invoices found." }] };
      }

      const rows = invoices.map((inv) =>
        [
          `ID: ${inv.id}`,
          `Ref: ${inv.name}`,
          `Customer: ${inv.partner_id?.[1] ?? "—"}`,
          `Date: ${inv.invoice_date ?? "—"}`,
          `Total: ${inv.amount_total} ${inv.currency_id?.[1] ?? ""}`,
          `Status: ${inv.state}`,
        ].join(" | ")
      );

      return {
        content: [
          {
            type: "text",
            text: `Found ${invoices.length} invoice(s):\n\n${rows.join("\n")}`,
          },
        ],
      };
    } catch (err) {
      return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
    }
  }
);

// ─── Tool: get_invoice ───────────────────────────────────────────────────────

server.tool(
  "get_invoice",
  "Get full details of a specific invoice by ID or reference number",
  {
    invoice_id: z.number().int().optional().describe("Odoo invoice numeric ID"),
    reference: z.string().optional().describe("Invoice reference e.g. INV/2026/00001"),
  },
  async ({ invoice_id, reference }) => {
    try {
      if (!invoice_id && !reference) {
        throw new Error("Provide either invoice_id or reference");
      }

      const uid = await authenticate();

      const domain = [["move_type", "=", "out_invoice"]];
      if (invoice_id) domain.push(["id", "=", invoice_id]);
      else domain.push(["name", "=", reference]);

      const invoices = await callKw(uid, "account.move", "search_read", [
        domain,
        [
          "id",
          "name",
          "partner_id",
          "invoice_date",
          "invoice_date_due",
          "amount_untaxed",
          "amount_tax",
          "amount_total",
          "state",
          "currency_id",
          "invoice_line_ids",
          "narration",
          "payment_state",
        ],
        0,
        1,
      ]);

      if (!invoices.length) throw new Error("Invoice not found");

      const inv = invoices[0];

      // Fetch line items
      const lines = await callKw(uid, "account.move.line", "search_read", [
        [["move_id", "=", inv.id], ["display_type", "=", "product"]],
        ["name", "quantity", "price_unit", "price_subtotal"],
      ]);

      const lineText = lines
        .map(
          (l) =>
            `  • ${l.name} | Qty: ${l.quantity} | Unit: ${l.price_unit} | Subtotal: ${l.price_subtotal}`
        )
        .join("\n");

      const detail = [
        `Invoice: ${inv.name}`,
        `Customer: ${inv.partner_id?.[1] ?? "—"}`,
        `Date: ${inv.invoice_date ?? "—"}`,
        `Due: ${inv.invoice_date_due ?? "—"}`,
        `Status: ${inv.state} | Payment: ${inv.payment_state}`,
        `Currency: ${inv.currency_id?.[1] ?? "—"}`,
        ``,
        `Lines:`,
        lineText || "  (none)",
        ``,
        `Subtotal: ${inv.amount_untaxed}`,
        `Tax: ${inv.amount_tax}`,
        `Total: ${inv.amount_total}`,
        inv.narration ? `\nNotes: ${inv.narration}` : "",
      ]
        .join("\n")
        .trim();

      return { content: [{ type: "text", text: detail }] };
    } catch (err) {
      return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
    }
  }
);

// ─── Start ───────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
