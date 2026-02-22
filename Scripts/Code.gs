/**
 * ============================================================
 * 🚀 SRV AI OUTREACH TOOL v29.0 (PRODUCTION)
 * ============================================================
 * Developer: Nampalli Srinivas
 * Company: CyberArc MSP
 * 
 * FIXES IN v36:
 * ✅ AI Date Context Injection (Fixes "wrong time/date" issue)
 * ✅ Dynamic Calendly URL (Auto-appends ?month=YYYY-MM)
 * ✅ Enhanced Header (Logo + "CyberArc MSP" text)
 * ============================================================
 */

const CONFIG = {
  APOLLO_KEY      : "e3az",      // 🔴 Set your Apollo API key
  GROQ_API_KEY    : "gsk_x4Dc",        // 🔴 Set your Groq API key (gsk_...)
  CALENDLY_URL    : "https://calendly.com/cyberarcmsp/30min", // 🔴 Set your Calendly link here
  SENDER_NAME     : "CyberArc MSP",
  SENDER_EMAIL    : "contact.cyberarcmsp@gmail.com",  // 🔴 Set your email
  SENDER_TITLE    : "Enterprise Solutions Architect",
  DAILY_LIMIT     : 5,
  EMAIL_DELAY_MS  : 65000
};

const SHEETS = {
  INPUT  : "Input_Leads",
  OUTBOX : "Outbox",
  REPLIED: "Replied",
  FAILED : "Failed"
};

const LEAD = {
  EMAIL:0, FIRST:1, LAST:2, COMPANY:3, ROLE:4, WEBSITE:5, LINKEDIN:6, LOCATION:7, SENIORITY:8, EMPLOYEES:9, INDUSTRY:10
};
const OUTBOX = { OBS:6, STATUS:7, TIMESTAMP:8, THREAD:9 };
const OUTBOX_COLS = 10;

// ============================================================
// 🤖  ENHANCED AI EMAIL GENERATOR
// ============================================================

function generateAIEmail(lead) {
  // v34: Using external prompt.gs for optimized prompt construction
  var promptText = constructPrompt(lead);


  try {
    var url = "https://api.groq.com/openai/v1/chat/completions";
    var payload = {
      "model": "moonshotai/kimi-k2-instruct-0905",
      "messages": [
        { "role": "system", "content": "You are a B2B email expert. Output only valid JSON." },
        { "role": "user", "content": promptText }
      ],
      "temperature": 0.7,
      "max_tokens": 1500,
      "top_p": 1,
      "stream": false
    };

    console.log("AI generating for: " + lead.company);

    var maxRetries = 3;
    var attempt = 0;
    var resp;
    var success = false;

    while (attempt < maxRetries && !success) {
      try {
        resp = UrlFetchApp.fetch(url, {
          method: "post",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + CONFIG.GROQ_API_KEY
          },
          payload: JSON.stringify(payload),
          muteHttpExceptions: true
        });

        if (resp.getResponseCode() === 429) {
          var waitTime = Math.pow(2, attempt) * 2000;
          console.warn("Rate limit, waiting " + waitTime + "ms");
          Utilities.sleep(waitTime);
          attempt++;
        } else if (resp.getResponseCode() !== 200) {
          Logger.log("Groq Error " + resp.getResponseCode() + ": " + resp.getContentText());
          throw new Error("API Error: " + resp.getResponseCode());
        } else {
          success = true;
        }
      } catch (e) {
        if (attempt === maxRetries - 1) throw e;
        attempt++;
        Utilities.sleep(1000);
      }
    }

    var json = JSON.parse(resp.getContentText());
    var content = json.choices[0].message.content;
    
    content = content.replace(/```json/g, "").replace(/```/g, "").trim();
    var start = content.indexOf('{');
    var end = content.lastIndexOf('}');
    if (start === -1 || end === -1) throw new Error("No JSON found");
    
    var parsed = JSON.parse(content.substring(start, end + 1));
    parsed.bodyHtml = wrapInTemplate(parsed.bodyHtml);
    
    if (parsed.subject.length > 60) parsed.subject = parsed.subject.substring(0, 57) + "...";

    return parsed;

  } catch(e) {
    console.error("AI failed: " + e.toString());
    throw e;
  }
}

function wrapInTemplate(innerHtml) {
  // v36: Dynamic Calendly Month
  var today = new Date();
  var yyyy = today.getFullYear();
  var mm = String(today.getMonth() + 1).padStart(2, '0'); // Jan is 0
  var calendlyUrl = CONFIG.CALENDLY_URL + "?month=" + yyyy + "-" + mm;

  var calendlyBtn = CONFIG.CALENDLY_URL ? 
    `<div style="margin: 30px 0; text-align: center;">
       <a href="${calendlyUrl}" style="display: inline-block; padding: 12px 24px; background-color: #0056b3; color: #ffffff; text-decoration: none; font-weight: 600; border-radius: 4px; font-size: 15px; letter-spacing: 0.5px;">📅 Book a Strategy Call</a>
     </div>` : "";

  return `
    <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f6f8; padding: 40px 0;">
      <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e1e4e8;">
        
        <!-- HEADER (Logo + Text) -->
        <div style="padding: 25px 40px; border-bottom: 2px solid #0056b3; background-color: #ffffff;">
          <table style="width: 100%; border-collapse: collapse;">
            <tr>
              <td style="width: 50px; vertical-align: middle;">
                <img src="https://cyberarcmsp.com/logo.png" alt="CyberArc MSP" style="width: 48px; height: auto; display: block;">
              </td>
              <td style="vertical-align: middle; padding-left: 15px;">
                <span style="font-size: 20px; font-weight: 700; color: #333333; letter-spacing: -0.5px;">CyberArc MSP</span>
              </td>
            </tr>
          </table>
        </div>

        <!-- CONTENT -->
        <div style="padding: 40px 40px 20px 40px; color: #333333; font-size: 16px; line-height: 1.6;">
          ${innerHtml}
        </div>

        <!-- CALL TO ACTION -->
        ${calendlyBtn}

        <!-- FOOTER -->
        <div style="background-color: #f8f9fa; padding: 30px 40px; border-top: 1px solid #eeeeee; font-size: 14px; color: #666666;">
          <table style="width: 100%; border-collapse: collapse;">
            <tr>
              <td style="vertical-align: top;">
                <p style="margin: 0 0 5px 0;"><strong style="color: #0056b3; font-size: 16px;">${CONFIG.SENDER_NAME}</strong></p>
                <p style="margin: 0 0 15px 0; color: #555;">${CONFIG.SENDER_TITLE}</p>
                
                <p style="margin: 0; line-height: 1.8;">
                  <a href="https://cyberarcmsp.com" style="color: #0056b3; text-decoration: none; font-weight: 500;">cyberarcmsp.com</a><br>
                  <a href="mailto:${CONFIG.SENDER_EMAIL}" style="color: #666666; text-decoration: none;">${CONFIG.SENDER_EMAIL}</a>
                </p>
              </td>
              <td style="text-align: right; vertical-align: top;">
                <p style="margin: 0; font-size: 12px; color: #999999;">
                  Global Operations<br>
                  Hyderabad • London • Dubai<br>
                  Toronto • Wyoming • Melbourne
                </p>
              </td>
            </tr>
          </table>
          
          <div style="margin-top: 20px; font-size: 11px; color: #aaaaaa; text-align: center;">
             © ${new Date().getFullYear()} CyberArc MSP. All rights reserved. <br>
             Privileged & Confidential.
          </div>
        </div>

      </div>
      
      <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #999999;">
        <p>To unsubscribe from these updates, simply reply "Unsubscribe".</p>
      </div>
    </div>
  `;
}

function buildFallback(lead) {
  var ctx = getSmartContext(lead);
  var subject = `Strategic resilience for ${lead.company}`;
  
  var content = "";
  if (ctx.key === "msp_manufacturing") {
    content = `<p>As a leader at ${lead.company}, you're balancing the technical demands of your manufacturing clients with your own operational growth. The risk of supply chain attacks targeting MSPs to pivot into industrial networks is at an all-time high.</p>`;
  } else if (ctx.key === "energy") {
    content = `<p>${ctx.location} is seeing rapid infrastructure shifts, but this expansion introduces critical risks in SCADA and OT environments. Convergence of IT/OT is where we see the biggest gaps.</p>`;
  } else {
    content = `<p>Digital transformation is accelerating across the ${lead.industry || "enterprise"} sector, but security maturity often lags behind operational expansion.</p>`;
  }

  var body = `
    <p>Hi ${lead.first},</p>
    ${content}
    <p>We help leaders at ${lead.company} close this gap. We've helped similar organizations:</p>
    <ul>
      <li><strong>Harden Infrastructure:</strong> We secure OT and IT environments without slowing down operations, ensuring continuous production uptime.</li>
      <li><strong>Implement Zero-Trust:</strong> We deploy strict access controls across global vendor ecosystems to prevent unauthorized entry.</li>
      <li><strong>Reduce Downtime:</strong> We utilize proactive defense mechanisms to neutralize ransomware threats before they impact revenue.</li>
    </ul>
    <p>Not as a compliance exercise—but as a continuity strategy.</p>
    <p>If you're open, I'd value 15 minutes to compare notes on how ${lead.company} is approaching resilience this year.</p>
  `;

  return {
    subject: subject,
    bodyHtml: wrapInTemplate(body)
  };
}

function rowToLead(row) {
  var u = unpackObservation(String(row[OUTBOX.OBS] || ""));
  return {
    email: String(row[LEAD.EMAIL] || "").trim(),
    first: String(row[LEAD.FIRST] || "").trim(),
    last: String(row[LEAD.LAST] || "").trim(),
    company: String(row[LEAD.COMPANY] || "").trim(),
    role: String(row[LEAD.ROLE] || "").trim(),
    website: String(row[LEAD.WEBSITE] || "").trim(),
    linkedin: u.linkedin, location: u.location, 
    seniority: u.seniority, industry: u.industry,
    employees: u.employees
  };
}

function unpackObservation(obsStr) {
  var out = { linkedin: "", location: "", seniority: "", employees: "", industry: "" };
  (obsStr || "").split(" | ").forEach(function(p) {
    if (p.indexOf("LinkedIn: ") === 0) out.linkedin = p.replace("LinkedIn: ", "");
    else if (p.indexOf("📍 ") === 0) out.location = p.replace("📍 ", "");
    else if (p.indexOf("Industry: ") === 0) out.industry = p.replace("Industry: ", "");
    else if (p.indexOf("Employees: ") === 0) out.employees = p.replace("Employees: ", "");
  });
  return out;
}

function htmlToPlain(html) {
  return html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

// ============================================================
// 📌  MENU
// ============================================================

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🚀 Srv AI Outreach Tool")
    .addItem("🔍 1. Fetch Leads (Apollo)", "fetchApolloLeads")
    .addItem("📥 2. Move to Outbox", "importLeadsToOutbox")
    .addItem("🤖 3. AI-Generate & Send", "generateAndSend")
    .addItem("🔄 4. Check Replies", "checkReplies")
    .addSeparator()
    .addItem("⏰ Enable Auto-Schedule", "setupAutomation")
    .addItem("🗑️ Stop Auto-Schedule", "removeAutomation")
    .addToUi();
}

function logOrAlert(message, title) {
  try {
    var ui = SpreadsheetApp.getUi(); 
    ui.alert(title || "Info", message, ui.ButtonSet.OK);
  } catch (e) {
    console.log("[LOG] " + (title ? title + ": " : "") + message);
  }
}

function getOrCreate(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    if (headers) {
      sh.appendRow(headers);
      sh.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#1565c0").setFontColor("white");
    }
  }
  return sh;
}

// ============================================================
// 🔍  APOLLO LEAD FETCHING (PRODUCTION)
// ============================================================

function fetchApolloLeads() {
  var ui = SpreadsheetApp.getUi();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  
  if (!CONFIG.APOLLO_KEY || CONFIG.APOLLO_KEY.length < 10) {
    ui.alert("⛔ Apollo Key Missing", "Set CONFIG.APOLLO_KEY in line 18", ui.ButtonSet.OK);
    return;
  }
  
  var titleResp = ui.prompt("🎯 Job Titles (1/4)", "Comma-separated:\nCEO, Founder | CISO | CTO", ui.ButtonSet.OK_CANCEL);
  if (titleResp.getSelectedButton() !== ui.Button.OK) return;
  
  var titles = titleResp.getResponseText().split(",").map(function(t) { return t.trim(); }).filter(Boolean);
  if (!titles.length) { ui.alert("❌", "Titles required", ui.ButtonSet.OK); return; }
  
  var indResp = ui.prompt("🏭 Industry (2/4)", "Optional. Examples: Fintech, Healthcare, SaaS", ui.ButtonSet.OK_CANCEL);
  if (indResp.getSelectedButton() !== ui.Button.OK) return;
  var industry = indResp.getResponseText().trim();
  
  var locResp = ui.prompt("📍 Location (3/4)", "Optional. Examples: UK, USA, India", ui.ButtonSet.OK_CANCEL);
  if (locResp.getSelectedButton() !== ui.Button.OK) return;
  var location = locResp.getResponseText().trim();
  
  var cntResp = ui.prompt("🔢 How Many? (4/4)", "1-15 leads", ui.ButtonSet.OK_CANCEL);
  if (cntResp.getSelectedButton() !== ui.Button.OK) return;
  var targetCount = Math.min(15, Math.max(1, parseInt(cntResp.getResponseText()) || 5));
  
  Logger.log("🎯 Target: " + targetCount + " leads | Credits will be used: ~" + targetCount);
  ss.toast("Searching Apollo (credit-efficient mode)...", "🔍 Apollo", 5);
  
  // Setup Sheet & Load Existing Emails
  var inputSheet = ss.getSheetByName(SHEETS.INPUT);
  if (!inputSheet) {
    inputSheet = ss.insertSheet(SHEETS.INPUT);
    inputSheet.appendRow(["Email", "First Name", "Last Name", "Company", "Role", "Website", "LinkedIn", "Location", "Seniority", "Employees", "Industry"]);
    inputSheet.getRange(1, 1, 1, 11).setFontWeight("bold").setBackground("#1565c0").setFontColor("white");
  }

  var existing = {};
  inputSheet.getDataRange().getValues().slice(1).forEach(function(r) {
    if (r[0]) existing[String(r[0]).toLowerCase().trim()] = true;
  });
  
  var HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "X-Api-Key": CONFIG.APOLLO_KEY
  };

  var rows = [];
  var page = 1;
  var maxPages = 20;
  var creditsUsed = 0;
  var duplicateCount = 0;
  var noEmailCount = 0;
  
  // CREDIT-EFFICIENT APPROACH: Only enrich what we need
  while (rows.length < targetCount && page <= maxPages) {
    ss.toast("Page " + page + ": " + rows.length + "/" + targetCount + " found | Credits: " + creditsUsed, "🔍 Searching", 30);
    
    // Search with exact count needed (plus buffer for duplicates)
    var neededCount = targetCount - rows.length;
    var searchCount = Math.min(neededCount + 3, 10); // Small buffer, max 10 per batch
    
    var searchPayload = {
      page: page, 
      per_page: searchCount,  // Only fetch what we need
      person_titles: titles,
      person_seniorities: ["c_suite", "vp", "director", "manager", "owner", "founder"],
      organization_num_employees_ranges: ["11,50", "51,200", "201,500", "501,1000"],
      contact_email_status: ["verified", "likely to engage"]
    };
    
    if (industry) searchPayload.q_organization_keyword_tags = [industry];
    if (location) searchPayload.person_locations = [location];
    
    Logger.log("--- PAGE " + page + " | Fetching " + searchCount + " people ---");
    
    try {
      // STEP 1: Search (FREE - no credits)
      var searchReq = UrlFetchApp.fetch("https://api.apollo.io/api/v1/mixed_people/api_search", {
        method: "post", 
        headers: HEADERS, 
        payload: JSON.stringify(searchPayload), 
        muteHttpExceptions: true
      });
      
      var searchCode = searchReq.getResponseCode();
      
      if (searchCode === 401) {
        ui.alert("❌ Invalid API Key", "Check CONFIG.APOLLO_KEY", ui.ButtonSet.OK);
        return;
      }
      
      if (searchCode === 429) {
        Utilities.sleep(5000);
        continue;
      }
      
      if (searchCode !== 200) {
        ui.alert("❌ Search Failed", searchReq.getContentText().substring(0, 200), ui.ButtonSet.OK);
        break;
      }
      
      var searchData = JSON.parse(searchReq.getContentText());
      var people = searchData.people || [];
      
      Logger.log("Search returned: " + people.length + " people");
      
      if (!people.length) {
        Logger.log("No more results");
        break;
      }
      
      var personIds = people.map(function(p) { return p.id; }).filter(Boolean);
      
      if (personIds.length === 0) {
        page++;
        continue;
      }
      
      // STEP 2: Enrich ONLY these IDs (COSTS CREDITS: 1 per person)
      Logger.log("💳 Enriching " + personIds.length + " people (costs " + personIds.length + " credits)");
      
      var enrichReq = UrlFetchApp.fetch("https://api.apollo.io/api/v1/people/bulk_match?reveal_personal_emails=true", {
        method: "post", 
        headers: HEADERS,
        payload: JSON.stringify({ details: personIds.map(function(id) { return { id: id }; }) }),
        muteHttpExceptions: true
      });
      
      var enrichCode = enrichReq.getResponseCode();
      
      if (enrichCode === 402) {
        ui.alert("💳 No Credits", "Out of enrichment credits", ui.ButtonSet.OK);
        break;
      }
      
      if (enrichCode !== 200) {
        var enrichErr = enrichReq.getContentText();
        Logger.log("Enrichment error: " + enrichErr);
        ui.alert("⚠️ Enrichment Failed", enrichErr.substring(0, 200), ui.ButtonSet.OK);
        break;
      }
      
      var enrichData = JSON.parse(enrichReq.getContentText());
      var matches = enrichData.matches || [];
      creditsUsed += matches.length;
      
      Logger.log("Enriched " + matches.length + " profiles (Total credits: " + creditsUsed + ")");
      
      // STEP 3: Process Results
      for (var i = 0; i < matches.length; i++) {
        if (rows.length >= targetCount) break;
        
        var p = matches[i];
        
        // Extract email
        var email = "";
        if (p.email) {
          email = p.email;
        } else if (Array.isArray(p.emails) && p.emails.length > 0) {
          var verified = p.emails.filter(function(e) { return e.email_status === "verified"; })[0];
          email = verified ? verified.email : p.emails[0].email;
        }
        
        if (!email) {
          noEmailCount++;
          Logger.log("⚠️ No email for: " + (p.first_name || "unknown"));
          continue;
        }
        
        // Skip duplicates
        if (existing[email.toLowerCase()]) {
          duplicateCount++;
          Logger.log("⚠️ Duplicate: " + email);
          continue;
        }
        
        // Extract data
        var org = p.organization || {};
        var loc = [p.city, p.state, p.country].filter(Boolean).join(", ");
        var emp = org.estimated_num_employees ? "~" + org.estimated_num_employees : "";
        
        var detectedInd = industry || (org.keywords && org.keywords.length ? org.keywords[0] : null);
        if (!detectedInd) {
          var txt = ((p.title || "") + " " + (org.name || "")).toLowerCase();
          if (txt.match(/health|medical|pharma/)) detectedInd = "Healthcare";
          else if (txt.match(/fintech|bank|payment/)) detectedInd = "Fintech";
          else if (txt.match(/saas|software/)) detectedInd = "SaaS";
          else if (txt.match(/manufact|factory/)) detectedInd = "Manufacturing";
          else if (txt.match(/energy|oil|gas/)) detectedInd = "Energy";
          else if (txt.match(/infra|construct/)) detectedInd = "Infrastructure";
          else detectedInd = "Technology";
        }
        
        rows.push([
          email, 
          p.first_name || "", 
          p.last_name || "", 
          org.name || "", 
          p.title || titles[0] || "", 
          org.website_url || "", 
          p.linkedin_url || "", 
          loc, 
          p.seniority || "", 
          emp, 
          detectedInd
        ]);
        
        existing[email.toLowerCase()] = true;
        Logger.log("✅ Added: " + email + " | " + (org.name || "unknown"));
      }
      
      page++;
      Utilities.sleep(800);
      
    } catch (e) {
      Logger.log("Error: " + e.toString());
      ui.alert("⚠️ Error", e.toString(), ui.ButtonSet.OK);
      break;
    }
  }
  
  // Final Summary
  Logger.log("=== COMPLETE ===");
  Logger.log("New leads: " + rows.length);
  Logger.log("Credits used: " + creditsUsed);
  Logger.log("Duplicates: " + duplicateCount);
  Logger.log("No email: " + noEmailCount);
  
  if (rows.length > 0) {
    inputSheet.getRange(inputSheet.getLastRow() + 1, 1, rows.length, 11).setValues(rows);
    
    var summary = "✅ Fetched " + rows.length + " leads!\n\n" +
                  "� Credits Used: " + creditsUsed + "\n" +
                  "📊 Duplicates skipped: " + duplicateCount + "\n" +
                  "⚠️ No email: " + noEmailCount;
    
    ui.alert("Success", summary, ui.ButtonSet.OK);
    
    var next = ui.alert("🚀 Next Step", "Move " + rows.length + " leads to Outbox?", ui.ButtonSet.YES_NO);
    if (next === ui.Button.YES) {
      importLeadsToOutbox();
    }
  } else {
    ui.alert("⚠️ No Leads Found", 
             "Credits used: " + creditsUsed + "\n" +
             "Duplicates: " + duplicateCount + "\n" +
             "No email: " + noEmailCount + "\n\n" +
             "Try different filters.", 
             ui.ButtonSet.OK);
  }
}


function importLeadsToOutbox() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var inSheet = ss.getSheetByName(SHEETS.INPUT);
  var outSheet = ss.getSheetByName(SHEETS.OUTBOX);
  if (!inSheet || !outSheet) { logOrAlert("Missing Sheets", "Error"); return; }
  
  var raw = inSheet.getDataRange().getValues();
  var leads = raw.slice(1).filter(function(r) { return r[0]; });
  if (!leads.length) { logOrAlert("No leads", "Info"); return; }
  
  var rows = leads.map(function(l) {
    var obs = [`📍 ${l[LEAD.LOCATION]}`, `Industry: ${l[LEAD.INDUSTRY]}`, `Employees: ${l[LEAD.EMPLOYEES]}`].join(" | ");
    return [l[LEAD.EMAIL], l[LEAD.FIRST], l[LEAD.LAST], l[LEAD.COMPANY], l[LEAD.ROLE], l[LEAD.WEBSITE], obs, "Pending", "", ""];
  });
  outSheet.getRange(outSheet.getLastRow()+1, 1, rows.length, OUTBOX_COLS).setValues(rows);
  inSheet.getRange(2, 1, inSheet.getLastRow(), inSheet.getLastColumn()).clearContent();
  logOrAlert("Moved " + rows.length + " leads", "Success");
}

// ============================================================
// 🤖  BATCH SEND
// ============================================================

function generateAndSend() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEETS.OUTBOX);
  var failSheet = getOrCreate(SHEETS.FAILED, ["Email", "Company", "Error", "Timestamp"]);
  var data = sheet.getDataRange().getValues();
  var sent = 0;

  console.log("Batch send starting...");

  if (!CONFIG.GROQ_API_KEY || CONFIG.GROQ_API_KEY.length < 20) {
    logOrAlert("Groq Key Missing", "Error"); return;
  }

  for (var i = 1; i < data.length; i++) {
    if (sent >= CONFIG.DAILY_LIMIT) break;
    if (!data[i][LEAD.EMAIL] || data[i][OUTBOX.STATUS] !== "Pending") continue;

    var lead = rowToLead(data[i]);
    console.log("Processing: " + lead.email);

    try {
      var pkg = generateAIEmail(lead);
      if (!pkg) pkg = buildFallback(lead);

      var plain = htmlToPlain(pkg.bodyHtml);
      var draft = GmailApp.createDraft(lead.email, pkg.subject, plain, {
        name: CONFIG.SENDER_NAME, htmlBody: pkg.bodyHtml
      });
      var sentMsg = draft.send();
      var thId = sentMsg.getThread().getId();

      var r = i + 1;
      sheet.getRange(r, OUTBOX.STATUS + 1).setValue("Sent");
      sheet.getRange(r, OUTBOX.TIMESTAMP + 1).setValue(new Date());
      sheet.getRange(r, OUTBOX.THREAD + 1).setValue(thId);
      sheet.getRange(r, 1, 1, OUTBOX_COLS).setBackground("#cfe2f3");
      sent++;

      if (sent < CONFIG.DAILY_LIMIT) Utilities.sleep(CONFIG.EMAIL_DELAY_MS);

    } catch (e) {
      console.error("Error: " + lead.email + " - " + e.message);
      var r = i + 1;
      sheet.getRange(r, OUTBOX.STATUS + 1).setValue("Error: " + e.message.substring(0, 100));
      sheet.getRange(r, 1, 1, OUTBOX_COLS).setBackground("#f4cccc");
      failSheet.appendRow([lead.email, lead.company, e.message, new Date()]);
    }
  }

  logOrAlert(sent > 0 ? "✅ " + sent + " sent" : "ℹ️ No pending", "Complete");
}

function checkReplies() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEETS.OUTBOX);
  var data = sheet.getDataRange().getValues();
  var myEmail = Session.getActiveUser().getEmail().toLowerCase();
  var count = 0;

  for (var i = 1; i < data.length; i++) {
    if (data[i][OUTBOX.STATUS] !== "Sent" || !data[i][OUTBOX.THREAD]) continue;
    try {
      var thread = GmailApp.getThreadById(data[i][OUTBOX.THREAD]);
      var msgs = thread.getMessages();
      if (msgs.length > 1 && msgs[msgs.length - 1].getFrom().toLowerCase().indexOf(myEmail) === -1) {
        var first = data[i][LEAD.FIRST] || "there";
        thread.reply(`Hi ${first},\n\nThanks for your note. Let me know a time that works.\n\nBest,\nCyberArc MSP`);
        sheet.getRange(i + 1, OUTBOX.STATUS + 1).setValue("Replied");
        sheet.getRange(i + 1, 1, 1, OUTBOX_COLS).setBackground("#b6d7a8");
        count++;
      }
    } catch (e) {}
  }
  if (count > 0) logOrAlert(count + " replies", "Detected");
}

function setupAutomation() {
  removeAutomation(true);
  ScriptApp.newTrigger("generateAndSend").timeBased().atHour(9).everyDays(1).create();
  ScriptApp.newTrigger("checkReplies").timeBased().atHour(13).everyDays(1).create();
  logOrAlert("Automation enabled: 9AM send, 1PM replies", "Active");
}

function removeAutomation(silent) {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) ScriptApp.deleteTrigger(triggers[i]);
  if (!silent) logOrAlert("Automation stopped", "Done");
}