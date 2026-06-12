<?php
/**
 * Renders the chatbot UI container and enqueues the widget assets.
 *
 * The widget JS calls the same-origin REST proxy (/wp-json/county-assistant/v1/chat)
 * with the REST nonce, so the APIM key stays server-side.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class County_Assistant_Widget {

    public function register(): void {
        add_action( 'wp_enqueue_scripts', array( $this, 'enqueue' ) );
        add_action( 'wp_footer', array( $this, 'render_container' ) );
        add_shortcode( 'county_assistant', array( $this, 'shortcode' ) );
    }

    public function enqueue(): void {
        $opts = get_option( COUNTY_ASSISTANT_OPT, array() );
        if ( ( $opts['enabled'] ?? '1' ) !== '1' ) {
            return;
        }

        wp_enqueue_style(
            'county-assistant',
            plugins_url( 'assets/widget.css', COUNTY_ASSISTANT_FILE ),
            array(),
            COUNTY_ASSISTANT_VERSION
        );

        wp_enqueue_script(
            'county-assistant',
            plugins_url( 'assets/widget.js', COUNTY_ASSISTANT_FILE ),
            array(),
            COUNTY_ASSISTANT_VERSION,
            true
        );

        // Pass the same-origin proxy URL + nonce to the front-end (no APIM key here).
        wp_localize_script(
            'county-assistant',
            'CountyAssistantConfig',
            array(
                'endpoint'     => esc_url_raw( rest_url( 'county-assistant/v1/chat' ) ),
                'siteEndpoint' => esc_url_raw( rest_url( 'county-assistant/v1/site' ) ),
                'nonce'        => wp_create_nonce( 'wp_rest' ),
                'greeting'     => sanitize_text_field( $opts['greeting'] ?? 'How can I help with county services?' ),
                'mode'         => 'proxy',
            )
        );
    }

    public function render_container(): void {
        $opts = get_option( COUNTY_ASSISTANT_OPT, array() );
        if ( ( $opts['enabled'] ?? '1' ) !== '1' ) {
            return;
        }
        echo '<div id="county-assistant-root" aria-live="polite"></div>';
    }

    /**
     * Optional shortcode to place an inline launcher in content.
     */
    public function shortcode( $atts ): string {
        return '<div class="county-assistant-inline" data-county-assistant-inline="1"></div>';
    }
}
