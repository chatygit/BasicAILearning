# Citi Security Training Quiz — Questions & Answers

> Running log of quiz questions and answers. Q3 (XSS for "not new in 2025 Citi Top 10") was marked incorrect in the quiz — noted below.

---

## Q1. n8n attack (January 2026)

**Q:** In January 2026, N8N product (low code, workflow solution) was hit with an attack that resulted in OAuth credentials being harvested and stolen from their users. What type of attack was it?

**A: Software Supply Chain Failures and Component (Third Party/Open Source) Analysis Reveals Vulnerabilities and Exploits**

Attackers published malicious npm packages masquerading as legitimate n8n community nodes (e.g., a fake Google Ads integration). Once installed, they decrypted stored OAuth tokens using n8n's master key and exfiltrated them during workflow execution — a supply chain attack weaponizing trust in third-party/open-source components.

---

## Q2. NOT a new vulnerability in the 2025 Citi Top 10 list

**Q:** Which of the below is NOT a new vulnerability in the 2025 Citi Top 10 Vulnerabilities list?
Options: Hardcoded Secrets / Cross-site Scripting / Component (Third Party/Open Source) Analysis / Mixed Contents (HTTP/HTTPS)

**A (my guess): Cross-site Scripting — ❌ marked INCORRECT by the quiz.**

The Citi list is internal and not publicly verifiable. Since XSS was wrong, the likely intended answer is **Component (Third Party/Open Source) Analysis Reveals Vulnerabilities and Exploits** (already present on earlier Citi lists), making XSS, Hardcoded Secrets, and Mixed Contents the new 2025 additions.

---

## Q3. Standardized API technology at Citi

**Q:** Which standardized API technology does Citi use to address and manage common API security risks?

**A: Representational State Transfer (REST)**

REST is Citi's enterprise-wide API standard (developer portal, CitiConnect). Standardizing on REST with consistent OAuth, TLS, gateway, and validation controls is how common API security risks are managed. gRPC/GraphQL are not the enterprise standard; SOAP is legacy.

---

## Q4. NOT an LLM/GenAI Top 10 risk

**Q:** Which of the following is NOT recognized as a Top 10 risk associated with LLMs and Generative AI applications?
Options: Sensitive Information Disclosure / Excessive Agency / Insufficient Logging and Monitoring / Unbounded Consumption

**A: Insufficient Logging and Monitoring**

Sensitive Information Disclosure (LLM02), Excessive Agency (LLM06), and Unbounded Consumption (LLM10) are all in the OWASP Top 10 for LLM Applications (2025). "Insufficient Logging and Monitoring" is from the classic OWASP web app Top 10 (A10:2017), not the LLM list.

---

## Q5. Vulnerability mitigated by crypto best practices

**Q:** Which vulnerability can be mitigated using best practices such as ensuring data is not transmitted in clear text, avoiding default crypto keys, and only using Citi approved ciphers?
Options: XSS / Path Manipulation–File Inclusion / Sensitive Information Obtained / Missing XML Validation

**A: Sensitive Information Obtained**

All three mitigations are cryptographic controls, which protect data confidentiality — i.e., they prevent attackers from obtaining sensitive information (classic sensitive data exposure / cryptographic failures category).

---

## Q6. Definition of "Data and Model Poisoning"

**Q:** Which of the following best describes the LLM risk known as "Data and Model Poisoning"?

**A: Malicious actors manipulating the LLM's training data or model parameters.**

That's LLM04 in the OWASP LLM Top 10: tampering with pre-training/fine-tuning/embedding data or model weights to introduce backdoors, bias, or degraded behavior. The other options describe Excessive Agency, System Prompt Leakage, and Improper Output Handling.

---

## Q7. NOT a mandated REST API security measure

**Q:** Which of the following security measures is NOT mandated by Citi for managing REST APIs?
Options: Publicly exposing non-public information in URLs / Least privilege / Timestamps on requests / API gateway

**A: Publicly exposing non-public information in URLs**

It's the only option that isn't a security measure at all — it's an anti-pattern (data in URLs leaks via logs, browser history, proxies). Least privilege, request timestamps (anti-replay), and API gateways are genuine mandated controls.

---

## Q8. Secure coding guidance document

**Q:** What covers guidance for secure coding practices around web applications, APIs and webservices, cloud-based applications and mobile applications?
Options: VTM / OSS Consumption Guidance / CVM–SCA / Citi Secure Coding Guidelines (SCG)

**A: Citi Secure Coding Guidelines (SCG)**

Secure *coding practices* guidance = secure coding guidelines. VTM manages identified vulnerabilities/threats, OSS Consumption governs open-source intake, CVM/SCA scans third-party components.

---

## Q9. Primary goal of the OWASP Top 10 Project

**Q:** What is the primary goal of the OWASP Top 10 Project?

**A: Highlight the most critical security risks to web applications and is an awareness document for web application security.**

Near-verbatim OWASP's own description. It is free and open (not paid), a curated data-driven document (not a discussion hub), and focused on broadly relevant risks (not controversial/opinion-driven ones).

---

## Q10. Best practice for sensitive data (PII, cards, health)

**Q:** When working with sensitive data such as PII, credit card numbers and health data what is a best practice to secure the data from access by bad actors?
Options: Use default crypto keys / Transmit in clear text / Treat same as non-sensitive / Only use Citi approved ciphers

**A: Only use Citi approved ciphers**

The only best practice among the four — the other three are all anti-patterns.

---

## Q11. Developer Self-Service vs Release Testing team

**Q:** Which statement best describes how Developer Self-Service and the Release Testing team contribute to application security testing?

**A: Developer Self-Service allows developers to find and fix security issues during development, while the Release Testing team performs manual and automated security testing during sprint and release cycles.**

Self-service shifts security left (early, during development); Release Testing provides formal manual + automated testing in sprint/release cycles. It complements, not replaces, independent release testing.

---

## Q12. Primary goal of the Citi System Security Testing Standard (SSTS)

**Q:** What is the primary goal of the SSTS document?

**A: The SSTS defines the mandatory requirements for security testing throughout the lifecycle of an application — from planning through post-production.**

It's a security *testing* standard. The other options describe an architecture standard, a logging/monitoring standard, and a data classification standard.

---

## Q13. AppSec services, knowledge sharing, collaboration tool

**Q:** Which of the following tools can Application Developers and Owners go to for AppSec Program Services, Knowledge Sharing, and Collaboration?
Options: Checkmarx / Black Duck / Contrast / Application Security Hub

**A: Application Security Hub**

A portal/community hub matches "program services, knowledge sharing, collaboration." Checkmarx = SAST, Black Duck = SCA, Contrast = IAST — scanning tools, not collaboration platforms.

---

## Q14. SDLC phases where SSTS requires onboarding & scanning

**Q:** During what SDLC phase(s) does the SSTS require all in-scope applications to be onboarded and scanned by?
Options: Production Phase / Build Phase / SSTS does not require scanning / Both Build and Production Phases

**A: Both Build and Production Phases**

Consistent with SSTS mandating testing from planning through post-production: onboard and scan during build, with obligations continuing in production.

---

## Q15. Governance & integration of security testing into SDLC

**Q:** Which program focuses on the governance and integration of security testing into the Software Development lifecycle for all applications identified as in-scope based on a risk-based approach?
Options: ASM / CVM / AVA / SAST

**A: Application Security Management (ASM)**

"Program" + "governance and integration" = a management-level function. SAST is a technique, CVM covers components, AVA is an assessment activity — all of which sit under the ASM program.

---

## Q16. NOT a key measure for mitigating backdoor risk

**Q:** Which of the following is NOT a key measure for mitigating the risk of backdoors in software and systems?
Options: Sanitize/validate all user inputs passed to other processes / Expose sensitive data through health monitoring services or endpoints / Implement access control per Citi's standard tools and guidelines / Adhere to proper change management processes

**A: Expose sensitive data through health monitoring services or endpoints**

That's a vulnerability, not a mitigation — the best practice is the opposite (lock down health/monitoring endpoints). Input sanitization, standard access control, and change management are all genuine backdoor mitigations.

---

## Q17. Where to find the Citi Cyber and Information Security Policy

**Q:** Where can an employee find the official Citi Cyber and Information Security Policy?
Options: From their manager (printed copy) / On the Citi internal network via the "Policies and Standards" portal / On a publicly accessible website / By contacting the Global Information Security Help Desk

**A: On the Citi internal network, accessible through the "Policies and Standards" portal**

The internal policy portal is the authoritative, always-current source. A printed copy would be unofficial/outdated, internal security policy is never public, and the help desk is for support, not policy distribution.

---

## Q18. Citi's definition of malicious code and backdoors

**Q:** How does Citi define malicious code and backdoors?

**A: Any code or functionality that allows a user to execute unapproved privileged functions that are not part of the business functionality.** (option 1)

Only definition broad enough for the combined "malicious code and backdoors" category. Option 2 is circular (uses "backdoor" in the definition); option 3 defines a virus (self-replicating); option 4 defines a Trojan (appears legitimate, intends harm).

---

## Q19. Consequences if a backdoor is found

**Q:** Introduction of malicious code violates the Citi Cyber and Information Security Policy. What consequences can result if a backdoor is found?
Options: Disciplinary action only, not leading to termination / Up to and including termination only if intentional / No disciplinary action, flagged for awareness and training / Disciplinary action up to and including termination

**A: Disciplinary action up to and including termination.** (option 4)

Standard compliance phrasing with no qualifier — the violation doesn't hinge on intent (negligently introducing a backdoor still violates policy), so the "only if intentional" option is the trap, and the other two understate the consequences.

---

## Q20. How a Privileged Access backdoor is introduced

**Q:** How might a Privileged Access backdoor be introduced into an application?
Options: Elevated privileges for specific users bypassing standard authentication / Access control via Citi standard tools / Special undocumented credentials in the database / Ensuring entry points have no hardcoded credentials

**A: By providing elevated privileges for specific users to bypass standard authentication mechanisms.** (option 1)

That's the definition of a privileged-access backdoor. Options 2 and 4 are mitigations, not introduction vectors; option 3 describes an undocumented-credentials backdoor (different flavor).

---

## Lab 1. Path Traversal (CWE-22) — AvatarServlet.java

**Task:** Demo the exploit, identify the traversal in `AvatarServlet.java`, remediate, and re-test.

**Vulnerability:** `Paths.get("./uploads", filename)` concatenates blindly — `getFile("../WEB-INF/web.xml")` resolves to `./WEB-INF/web.xml`, escaping the uploads directory and leaking sensitive files.

**Fix (normalize + containment check):**

```java
public Path getFile(String filename) {
    Path baseDir = Paths.get("./uploads").toAbsolutePath().normalize();
    Path path = baseDir.resolve(filename).normalize();
    if (!path.startsWith(baseDir)) {
        throw new IllegalArgumentException("Invalid file path: " + filename);
    }
    return path;
}
```

Key: `normalize()` collapses `../` first, then `startsWith(baseDir)` rejects anything that escaped. Alternative: `baseDir.resolve(Paths.get(filename).getFileName().toString())` to strip all directory components. Blocklisting the literal `../` string alone is insufficient (encoded variants, backslashes). In the servlet, return 400/404 on rejection.

**Actual AvatarServlet.java fix** — vulnerable line was `Path path = Paths.get(basePath, filename);` after `String basePath = req.getServletContext().getRealPath("avatar");`. Replacement:

```java
String basePath = req.getServletContext().getRealPath("avatar");
Path baseDir = Paths.get(basePath).toAbsolutePath().normalize();

Path path = baseDir.resolve(filename).normalize();
if (!path.startsWith(baseDir)) {
    resp.setStatus(HttpServletResponse.SC_BAD_REQUEST);
    return;
}

File file = path.toFile();
```

Rest of doGet (null-check 400, !exists 404, file serving) unchanged; no new imports needed.

---

## Q21. What does CSP stand for?

**Q:** What does CSP stand for?
Options: Content Service Protocol / Control Severe Policy / Content Security Policy / Content Strict Policy

**A: Content Security Policy** (option 3)

The browser standard delivered via the `Content-Security-Policy` header — whitelists allowed sources for scripts/styles/images, a defense-in-depth layer against XSS. The other expansions aren't real terms.

---

## Q22. Header that parses HTML to detect/prevent XSS

**Q:** Which header parses HTML to detect and prevent cross-site scripting attacks?
Options: HTML sanitizer / HTML parser / X-XSS Protection / CSP URL directive

**A: X-XSS Protection** (option 3)

`X-XSS-Protection` triggers the browser's XSS auditor, which parses the page to detect and block reflected XSS. Only actual header among the options (sanitizers/parsers are libraries; a CSP directive is not a header). Note: deprecated in modern browsers in favor of CSP, but it's the expected training answer.

---

## Q23. CSP directive created to replace X-XSS-Protection

**Q:** Which Content Security Policy directive was created to replace the X-XSS-Protection directive?
Options: unsafe-inline / xss-block / report uri / CSP URL directive

**A: unsafe-inline** ✅ (option 1) — *my initial pick of xss-block was ❌ wrong; quiz confirmed unsafe-inline.*

The quiz follows MDN's guidance: the modern replacement for `X-XSS-Protection` is a Content-Security-Policy that disallows `unsafe-inline` scripts — so `unsafe-inline` is the directive/keyword they key on. (Historical trivia: CSP Level 2 also drafted a `reflected-xss` directive for this, but that's not what the training uses.)

---

## Q24. What CSP directives, hashes, and nonces use to evaluate scripts

**Q:** What do Content Security Policy directives, hashes, and nonces use to evaluate whether scripts should run?
Options: Logs / Script checkers / Scanners / Allowlists

**A: Allowlists** (option 4)

CSP is allowlist-based: `script-src` enumerates permitted sources; hashes/nonces extend the allowlist to specific inline scripts. Anything not allowlisted is blocked by default. Logs/checkers/scanners are detection tools, not CSP's evaluation mechanism.

---

## Q25. Recommended X-XSS-Protection config for legacy browsers

**Q:** For legacy browsers, what's the recommended X-XSS-Protection configuration?
Options: xss-block / 1; report=&lt;reporting-uri&gt; / 1; mode=block / None of these options

**A: 1; mode=block** (option 3)

MDN's guidance: for legacy browsers use `X-XSS-Protection: 1; mode=block` — blocks the page entirely on detection instead of sanitizing (sanitize mode could itself introduce vulns). `report=` is a Chrome-only reporting variant; "xss-block" isn't a valid value.

---

## Q26. Feature used by X-XSS-Protection: 1; report=

**Q:** Which feature does the `X-XSS-Protection: 1; report=` use?
Options: report-uri / report-safe / strict-report

**A: report-uri** (option 1)

MDN: the Chromium-only `1; report=<reporting-URI>` mode sanitizes the page and reports the violation using the functionality of the CSP `report-uri` directive. The other two aren't real features.

---

## Q27. CSP replacement for X-XSS-Protection configuration

**Q:** What can you utilize in a Content Security Policy to replace the X-XSS-Protection configuration?
Options: XSS parsers / Secure dependencies / Nonces and hashes / Passwords

**A: Nonces and hashes** (option 3)

Replacing X-XSS-Protection with CSP means disallowing `unsafe-inline`; nonces and hashes then allow legitimate inline scripts (script runs only if it carries the policy nonce or matches an allowlisted hash), so injected scripts can't execute. The other options aren't CSP mechanisms.

---

## Q28. Most secure way of ensuring server/web application safety

**Q:** What's the most secure way of ensuring server or web application safety?
Options: Using security updates / Having secure architecture / Implementing firewalls / Using CSP directives

**A: Having secure architecture** (option 2)

Secure-by-design eliminates whole vulnerability classes; updates, firewalls, and CSP headers are partial/reactive defense-in-depth layers that supplement a secure architecture.

---

## Q29. Attacks X-XSS-Protection is ineffective against

**Q:** Against which type of attacks is the use of X-XSS-Protection ineffective?
Options: Cross-site request forgery / HTTP leakage / HTTP policy / DOM and stored XSS

**A: DOM and stored XSS** (option 4)

The XSS auditor compares rendered scripts against the request, so it only catches reflected XSS. Stored payloads (from the DB) and DOM-based payloads (assembled client-side) never appear in the request — a key reason the header was deprecated in favor of CSP.

---

## Q30. Effect of X-XSS-Protection: 0

**Q:** What's disabled by setting the XSS-Protection HTTP header to 0?
Options: XSS filtering / XSS attacks / DOM attacks / SQL injection

**A: XSS filtering** (option 1)

`X-XSS-Protection: 0` disables the browser's XSS filter/auditor — the documented meaning of the value. You can't "disable attacks" with a header, and SQLi is server-side.

---

## Lab 2. Command Injection (CWE-78) — SettingsServlet.java

**Vulnerability:** `getCurrentDate` ran `execCmd(new String[]{"/bin/sh", "-c", "date +'" + format + "'"})` with the user-controlled `date_format` request parameter — shell command injection.

**Fix — SettingsServlet.java:**

```java
private static final String DEFAULT_DATE_FORMAT = "yy-MM-dd HH:mm:ss";

public static String getCurrentDate(String format) {
    DateFormat dateFormat = new SimpleDateFormat(format);
    return dateFormat.format(new Date());
}
// delete execCmd() entirely
// add imports: java.text.DateFormat, java.text.SimpleDateFormat, java.util.Date
// remove imports: java.io.InputStream, java.io.IOException, java.util.Scanner
```

**Fix — settings.jsp select options:**

```jsp
<option value="yy-MM-dd HH:mm:ss">year-month-day</option>
<option value="dd-MM-yy HH:mm:ss">day-month-year</option>
<option value="MM-dd-yy HH:mm:ss">month-day-year</option>
```

No process spawned → no shell for metacharacters to reach; bad formats throw `IllegalArgumentException` instead of executing.

**Gotcha:** `getCurrentDate(String format)` must use the `format` param, NOT `DEFAULT_DATE_FORMAT` — `new SimpleDateFormat(format)`. Otherwise all three dropdown options render identically and the format test fails. Also ensure `DEFAULT_DATE_FORMAT` is the Java pattern `"yy-MM-dd HH:mm:ss"`, not the shell `"%y-%m-%d %H:%M:%S"`, so the fallback doesn't throw.

---

## Lab 3. XXE (CWE-611) — RouteParser.java

**Vulnerability:** `DocumentBuilderFactory.newInstance()` with default settings around line 30 — resolves external entities, enabling file disclosure / SSRF via crafted DOCTYPE.

**Fix (inside the existing try, before newDocumentBuilder):**

```java
DocumentBuilderFactory dbFactory = DocumentBuilderFactory.newInstance();
dbFactory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
dbFactory.setFeature("http://xml.org/sax/features/external-general-entities", false);
dbFactory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
dbFactory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
dbFactory.setXIncludeAware(false);
dbFactory.setExpandEntityReferences(false);
DocumentBuilder dBuilder = dbFactory.newDocumentBuilder();
Document doc = dBuilder.parse(inputStream);
```

`disallow-doctype-decl` is the OWASP primary defense (kills XXE + billion-laughs); the rest are belt-and-braces per the OWASP XXE Prevention Cheat Sheet. No new imports.

---

## Lab 4. Stored XSS — forgot-password.jsp line 21

**Vulnerability:** user-controlled value emitted raw via EL/scriptlet on line 21 → stored payload renders as HTML/JS.

**Fix:** JSTL output encoding.

1. Taglib at top (if missing): `<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>`
2. Wrap the raw expression: `${expr}` → `<c:out value="${expr}" />` (each dynamic field individually).

`<c:out>` HTML-encodes by default (`<` → `&lt;`), so payloads display as inert text.

---

## Lab 5. Sensitive Data Exposure — FileDownloadServlet parameters (guessing exercise)

**Q:** What are the HTTP parameters necessary to upload/download a file? (header says "upload"; body describes a FileDownloadServlet download — go with download)

**ANSWER (confirmed): `path,file`**

Discovered by probing the endpoint: `?path=test` → "File and path cannot be null" (file missing); `?path=test&file=test` → "Incorrect path /var/lib/tomcat9" (both params accepted, base dir leaked). So the two params are `path` and `file`.

Exploit half: `path` is validated against a base, `file` is unsanitized → directory traversal:
`curl -si "$T/FileDownloadServlet?path=/var/lib/tomcat9&file=../../../etc/passwd"`

**Install path of the web application:** `/var/lib/tomcat9` (leaked by the "Incorrect path /var/lib/tomcat9" error — Tomcat 9 CATALINA_BASE). Fallback if they want the deployed app dir: `/var/lib/tomcat9/webapps/ROOT`.

---

## Lab 6. SQL Injection — UserRepository.java login (lines 67–70)

**Vulnerability:** raw string-concatenated login query → SQLi (`admin` / `blah' or '1'='1`).

**Fix:** parameterized query (already mostly written in the lab). Critical gotcha — **line 70 must assign the PreparedStatement to `stmt`:**

```java
String query = "SELECT * FROM User WHERE username = ? AND password = ?";
String hashedPassword = PasswordUtils.hashPassword(password);
stmt = connection.prepareStatement(query);   // <-- missing "stmt =" caused NPE
stmt.setString(1, userName);
stmt.setString(2, hashedPassword);
rs = stmt.executeQuery();
```

Symptom of the missing assignment: deploy log shows "Application is NOT WORKING" — `stmt` null → NPE on setString → no JSESSIONID, /dashboard 302. Adding `stmt =` fixes it.
