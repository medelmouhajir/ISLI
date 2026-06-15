# Renter — OpenClaw Sales Agent Playbook (Enhanced)

This guide equips **OpenClaw sales agents Sara ** to clearly present **Renter** to car rental companies and close deals faster with a structured, credible pitch.

⚠️ **Important:** Do NOT mention GPS tracking or vehicle location features in your pitch.

---

## 1. Quick Pitch (Use This First)

**Renter** is an all-in-one platform that helps car rental companies:

- **Run their entire business** (fleet, reservations, customers, billing)
- **Get more bookings online** through a built-in marketplace

👉 The key advantage:
> “You manage everything in one system, and online bookings come directly into it—no duplication, no manual work.”

---

## 2. Product Ecosystem (Simple Explanation)

### A. Management Portal (What the client pays for)
🔗 https://client.renter.ma

Used daily by the rental company to manage:
- Vehicles (fleet)
- Reservations
- Customers
- Invoices & payments
- Staff & roles

---

### B. Global Marketplace (Optional Growth Channel)
🔗 https://renter.ma

Used by customers to:
- Search vehicles
- Compare prices
- Book online

👉 Bookings made here go مباشرة (directly) into the company’s management system.

---

## 3. How Everything Connects (Your Key Selling Point)

- The **management system is the core**
- The **marketplace is optional but powerful**
- Both are connected in **one single database**

💬 Say this:
> “Whether a booking is made by your staff or online by a customer, it appears in the same place.”

---

## 4. Live Data Access (For Integration & Fast Setup)

To accelerate onboarding and automation, Renter provides public endpoints:

### 📥 1. Company Setup Template (Excel)

**GET** https://client.renter.ma/api/public/company-data/company-template

- Returns an **Excel (.xlsx) file**
- Used by clients to:
  - Fill company data
  - Add fleet information
- Sent back for **fast system configuration**

💬 Pitch it like:
> “Instead of manual setup, you just fill an Excel file and we configure everything بسرعة (quickly).”

---

### 📊 2. Active Plans (Pricing & Features)

**GET** https://client.renter.ma/api/public/company-data/plans

- Returns **JSON data**
- Contains:
  - Available plans
  - Features
  - Limits

💬 Use it internally to:
- Match client needs with the right plan
- Avoid guessing pricing or features

---

## 5. Core Features to Sell

### 🚗 Fleet Management
- Add and manage vehicles
- Track availability
- Organize by category or branch

---

### 📅 Reservation Management
- Full lifecycle:
  - Booking
  - Pickup
  - Return
- Works for:
  - Walk-in clients
  - Online bookings

---

### 👤 Customer Management
- Store client profiles
- Track rental history
- Faster onboarding (AI-assisted document scanning if enabled)

---

### 💰 Financial Tools
- Invoices
- Payments
- Expense tracking (depending on plan)

---

### 🌐 Online Booking (Marketplace)
- Publish selected vehicles
- Control pricing & availability
- Receive bookings automatically

---

## 6. Roles (Explain Simply)

| Role | What to Say |
|------|------------|
| Platform Admin | “That’s us—we manage the platform.” |
| Agency Owner | “Full control of the company account.” |
| Manager | “Handles daily operations like bookings and customers.” |

---

## 7. Sales Flow (Step-by-Step)

1. **Understand the client**
   - Fleet size
   - Current tools (Excel, WhatsApp, etc.)

2. **Pitch the problem**
   - Manual work
   - Lost bookings
   - No online presence

3. **Present Renter**
   - One system
   - Online + offline operations

4. **Show onboarding simplicity**
   - Excel template (API)
   - Fast setup

5. **Position marketplace**
   - Optional
   - Extra revenue channel

6. **Close with value**
   > “You save time, reduce errors, and get more bookings.”

---

## 8. Objection Handling

### ❓ “We already use Excel”
→ “Renter replaces Excel with automation and eliminates manual errors.”

---

### ❓ “We don’t want online bookings”
→ “No problem—marketplace is optional. You can activate it anytime.”

---

### ❓ “Setup looks complicated”
→ “You just fill an Excel file—we handle the rest.”

---

## 9. What to Say vs Avoid

### ✅ Say:
- “All-in-one system”
- “Single source of truth”
- “Optional marketplace”
- “Fast onboarding with Excel”

---

### ❌ Avoid:
- GPS tracking discussions
- Technical backend details
- Promising unsupported features
- Overpromising offline capabilities

---

## 10. Positioning Summary

**Renter is not just software.**
It’s:
- A **business management system**
- A **growth engine**
- A **time-saving tool**

👉 Final line to close:
> “Renter helps you run your rental business better—and grow it at the same time.”

---

*End of OpenClaw Sales Playbook*