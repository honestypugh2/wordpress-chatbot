<?php
/**
 * County of Westvale (Demo) — front page template.
 *
 * Synthetic county-government homepage. All content is fictional. The County
 * Assistant chat launcher is injected by the county-assistant plugin (wp_footer).
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}
?>
<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
  <meta charset="<?php bloginfo( 'charset' ); ?>" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>

  <!-- Utility bar -->
  <div class="gov-utility">
    <div class="wrap">
      <span>An official synthetic demo of the County of Westvale</span>
      <span class="links">
        <a href="#">Translate</a>
        <a href="#">Contact</a>
        <a href="#">Pay Online</a>
      </span>
    </div>
  </div>

  <!-- Masthead -->
  <header class="gov-masthead">
    <div class="wrap">
      <div class="gov-seal">WV</div>
      <div class="gov-brand">
        <h1>County of Westvale</h1>
        <p>Serving residents of Westvale County</p>
      </div>
      <form class="gov-search" onsubmit="return false;">
        <input type="text" placeholder="Search county services&hellip;" aria-label="Search" />
        <button type="submit">Search</button>
      </form>
    </div>
  </header>

  <!-- Primary navigation -->
  <nav class="gov-nav">
    <div class="wrap">
      <a href="#" class="active">Home</a>
      <a href="#">Residents</a>
      <a href="#">Permits &amp; Licenses</a>
      <a href="#">Property &amp; Taxes</a>
      <a href="#">Health Services</a>
      <a href="#">Elections</a>
      <a href="#">Departments</a>
    </div>
  </nav>

  <!-- Hero -->
  <section class="gov-hero">
    <div class="wrap">
      <h2>Welcome to Westvale County</h2>
      <p>Find permits, pay property taxes, register to vote, and connect with county
         departments &mdash; online, anytime. Need help finding something? Ask the County
         Assistant in the corner.</p>
      <a class="cta" href="#services">Explore County Services</a>
    </div>
  </section>

  <!-- Quick services -->
  <section class="section" id="services">
    <div class="wrap">
      <h3>Popular Services</h3>
      <p class="sub">The things residents ask about most.</p>
      <div class="cards">
        <a class="card" href="#"><div class="ico">&#127959;&#65039;</div><h4>Building Permits</h4><p>Apply, check status, and view fees for land-use permits.</p></a>
        <a class="card" href="#"><div class="ico">&#128181;</div><h4>Property Taxes</h4><p>Due dates, payment options, and assessment appeals.</p></a>
        <a class="card" href="#"><div class="ico">&#128499;&#65039;</div><h4>Elections &amp; Voting</h4><p>Register to vote, find your polling place, and key dates.</p></a>
        <a class="card" href="#"><div class="ico">&#127973;</div><h4>Public Health</h4><p>Clinics, immunizations, and environmental health.</p></a>
        <a class="card" href="#"><div class="ico">&#128736;&#65039;</div><h4>Report a Concern</h4><p>Potholes, code issues, and road maintenance via 311.</p></a>
        <a class="card" href="#"><div class="ico">&#128187;</div><h4>Online Services</h4><p>Self-service portals for residents and businesses.</p></a>
      </div>
    </div>
  </section>

  <!-- Two-column content -->
  <section class="section">
    <div class="wrap grid2">
      <div class="panel news">
        <h3>County News &amp; Notices</h3>
        <ul>
          <li><span class="date">June 5, 2026</span><a href="#">Fiscal year 2027 budget hearings open for public comment</a></li>
          <li><span class="date">May 28, 2026</span><a href="#">Westvale 311 portal adds real-time service-request tracking</a></li>
          <li><span class="date">May 19, 2026</span><a href="#">Summer immunization clinics scheduled at three locations</a></li>
        </ul>
      </div>
      <aside>
        <div class="alert">
          <strong>Service alert:</strong> The Recorder's Office will close at noon on
          June 14 for system maintenance. Online services remain available.
        </div>
        <div class="panel" style="margin-top:16px;">
          <h3 style="margin-top:0;">Need help?</h3>
          <p style="color:var(--gov-muted); font-size:14px;">
            Use the <strong>County Assistant</strong> chat button at the bottom-right
            to get grounded answers about county services, with sources.
          </p>
        </div>
      </aside>
    </div>
  </section>

  <!-- Footer -->
  <footer class="gov-footer">
    <div class="wrap">
      <div><h5>Government</h5><a href="#">Board of Supervisors</a><a href="#">Departments</a><a href="#">Meetings &amp; Agendas</a></div>
      <div><h5>Residents</h5><a href="#">Permits</a><a href="#">Property &amp; Taxes</a><a href="#">Elections</a></div>
      <div><h5>Services</h5><a href="#">Pay Online</a><a href="#">Report a Concern</a><a href="#">Public Health</a></div>
      <div><h5>Connect</h5><a href="#">Contact Us</a><a href="#">Newsroom</a><a href="#">Accessibility</a></div>
    </div>
  </footer>
  <div class="gov-legal"><div class="wrap">Synthetic demo &bull; County of Westvale &bull; Not an official government website &bull; All content fictional.</div></div>

<?php wp_footer(); ?>
</body>
</html>
