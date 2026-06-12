<?php
/**
 * Same-origin REST proxy: WordPress -> APIM -> Foundry backend.
 *
 * Why a proxy:
 *  - Keeps the APIM subscription key on the server (never in the browser).
 *  - Lets the browser call a same-origin endpoint (no third-party CORS).
 *  - Provides a place to enforce a nonce, sanitize input, and shape errors.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class County_Assistant_Rest_Proxy {

    public function register(): void {
        add_action( 'rest_api_init', array( $this, 'register_routes' ) );
    }

    public function register_routes(): void {
        register_rest_route(
            'county-assistant/v1',
            '/chat',
            array(
                'methods'             => 'POST',
                'callback'            => array( $this, 'handle_chat' ),
                'permission_callback' => array( $this, 'check_nonce' ),
                'args'                => array(
                    'message' => array(
                        'required'          => true,
                        'type'              => 'string',
                        'sanitize_callback' => 'sanitize_textarea_field',
                    ),
                    'session_id' => array(
                        'required'          => false,
                        'type'              => 'string',
                        'sanitize_callback' => 'sanitize_text_field',
                    ),
                ),
            )
        );

        // Read-only site profile: lets the widget self-configure its title and
        // greeting on load so they follow the backend's DEMO_SITE_PROFILE. The
        // call is proxied server-side so the APIM key stays off the browser.
        register_rest_route(
            'county-assistant/v1',
            '/site',
            array(
                'methods'             => 'GET',
                'callback'            => array( $this, 'handle_site' ),
                'permission_callback' => array( $this, 'check_nonce' ),
            )
        );
    }

    /**
     * Validate the REST nonce sent by the front-end widget.
     */
    public function check_nonce( WP_REST_Request $request ): bool {
        $nonce = $request->get_header( 'X-WP-Nonce' );
        return (bool) wp_verify_nonce( $nonce, 'wp_rest' );
    }

    public function handle_chat( WP_REST_Request $request ): WP_REST_Response {
        $opts = get_option( COUNTY_ASSISTANT_OPT, array() );
        $url  = $opts['apim_url'] ?? '';
        $key  = $opts['apim_subscription'] ?? '';

        if ( empty( $url ) ) {
            return new WP_REST_Response(
                array( 'error' => array( 'code' => 'not_configured', 'message' => 'Assistant is not configured.' ) ),
                503
            );
        }

        $message    = (string) $request->get_param( 'message' );
        $session_id = (string) $request->get_param( 'session_id' );

        if ( '' === trim( $message ) ) {
            return new WP_REST_Response(
                array( 'error' => array( 'code' => 'empty', 'message' => 'Please enter a question.' ) ),
                400
            );
        }

        $correlation_id = wp_generate_uuid4();

        $response = wp_remote_post(
            $url,
            array(
                // Bing/AI-Search grounding routes through a Foundry agent; the first
                // call after a pattern switch (cold thread init) can take well over
                // 30s. Use a generous timeout so slow grounded answers don't surface
                // as a 502 "temporarily unavailable" in the widget.
                'timeout' => 90,
                'headers' => array_filter(
                    array(
                        'Content-Type'             => 'application/json',
                        'X-Correlation-Id'         => $correlation_id,
                        'Ocp-Apim-Subscription-Key'=> $key ?: null,
                    )
                ),
                'body'    => wp_json_encode(
                    array(
                        'message'    => $message,
                        'session_id' => $session_id ?: null,
                        'page_url'   => esc_url_raw( (string) $request->get_header( 'referer' ) ),
                    )
                ),
            )
        );

        if ( is_wp_error( $response ) ) {
            return new WP_REST_Response(
                array( 'error' => array( 'code' => 'upstream_error', 'message' => 'The assistant is temporarily unavailable.' ) ),
                502
            );
        }

        $code = (int) wp_remote_retrieve_response_code( $response );
        $body = json_decode( wp_remote_retrieve_body( $response ), true );

        return new WP_REST_Response( is_array( $body ) ? $body : array(), $code ?: 200 );
    }

    /**
     * Proxy the backend's active site profile (GET /site) so the widget can
     * self-configure its title/greeting from the live DEMO_SITE_PROFILE.
     */
    public function handle_site( WP_REST_Request $request ): WP_REST_Response {
        $opts = get_option( COUNTY_ASSISTANT_OPT, array() );
        $url  = $opts['apim_url'] ?? '';
        $key  = $opts['apim_subscription'] ?? '';

        // The site endpoint sits next to the chat endpoint on the same API path
        // (…/assistant/chat -> …/assistant/site).
        $site_url = preg_replace( '#/chat/?$#', '/site', (string) $url );

        if ( empty( $site_url ) ) {
            return new WP_REST_Response(
                array( 'error' => array( 'code' => 'not_configured', 'message' => 'Assistant is not configured.' ) ),
                503
            );
        }

        $response = wp_remote_get(
            $site_url,
            array(
                'timeout' => 15,
                'headers' => array_filter(
                    array(
                        'Accept'                    => 'application/json',
                        'Ocp-Apim-Subscription-Key' => $key ?: null,
                    )
                ),
            )
        );

        if ( is_wp_error( $response ) ) {
            // Non-fatal: the widget keeps its default title/greeting.
            return new WP_REST_Response(
                array( 'error' => array( 'code' => 'upstream_error', 'message' => 'Site profile unavailable.' ) ),
                502
            );
        }

        $code = (int) wp_remote_retrieve_response_code( $response );
        $body = json_decode( wp_remote_retrieve_body( $response ), true );

        return new WP_REST_Response( is_array( $body ) ? $body : array(), $code ?: 200 );
    }
}
