<?php
/**
 * Plugin Name:       County Assistant (Prototype)
 * Plugin URI:        https://county-portal.example.gov
 * Description:       Embeds the County Assistant chatbot and proxies requests to the Azure AI Foundry backend via APIM. Prototype for county-government demonstration.
 * Version:           0.2.0
 * Requires at least: 6.2
 * Requires PHP:      8.0
 * Author:            County of Westvale (fictional)
 * License:           MIT
 * Text Domain:       county-assistant
 *
 * SECURITY NOTES (prototype):
 *  - The APIM subscription key is stored server-side and never exposed to the browser.
 *  - Front-end calls hit a same-origin WordPress REST proxy that validates a nonce.
 *  - Input is sanitized; output to the page is escaped.
 *  - This is a skeleton; harden auth, rate limiting, and logging before production.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit; // No direct access.
}

define( 'COUNTY_ASSISTANT_VERSION', '0.2.0' );
define( 'COUNTY_ASSISTANT_OPT', 'county_assistant_options' );
define( 'COUNTY_ASSISTANT_FILE', __FILE__ );

require_once __DIR__ . '/includes/class-settings.php';
require_once __DIR__ . '/includes/class-rest-proxy.php';
require_once __DIR__ . '/includes/class-widget.php';

/**
 * Boot the plugin.
 */
function county_assistant_bootstrap(): void {
    ( new County_Assistant_Settings() )->register();
    ( new County_Assistant_Rest_Proxy() )->register();
    ( new County_Assistant_Widget() )->register();
}
add_action( 'plugins_loaded', 'county_assistant_bootstrap' );

/**
 * Sensible defaults on activation.
 */
function county_assistant_activate(): void {
    if ( false === get_option( COUNTY_ASSISTANT_OPT ) ) {
        add_option(
            COUNTY_ASSISTANT_OPT,
            array(
                'apim_url'             => '',
                'apim_subscription'    => '', // stored server-side only
                'enabled'              => '1',
                'greeting'             => 'Hi! I can help with county services. Ask me anything.',
            )
        );
    }
}
register_activation_hook( __FILE__, 'county_assistant_activate' );
