<?php
/**
 * Settings page for the County Assistant plugin.
 *
 * Stores the APIM endpoint and (server-side only) subscription key. The key is
 * never printed back to the browser or exposed via the proxy response.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class County_Assistant_Settings {

    public function register(): void {
        add_action( 'admin_menu', array( $this, 'add_menu' ) );
        add_action( 'admin_init', array( $this, 'register_settings' ) );
    }

    public function add_menu(): void {
        add_options_page(
            __( 'County Assistant', 'county-assistant' ),
            __( 'County Assistant', 'county-assistant' ),
            'manage_options',
            'county-assistant',
            array( $this, 'render_page' )
        );
    }

    public function register_settings(): void {
        register_setting(
            'county_assistant_group',
            COUNTY_ASSISTANT_OPT,
            array( $this, 'sanitize' )
        );
    }

    /**
     * Sanitize all settings before persisting.
     *
     * @param array<string,mixed> $input Raw input.
     * @return array<string,string>
     */
    public function sanitize( $input ): array {
        $existing = get_option( COUNTY_ASSISTANT_OPT, array() );

        $clean                    = array();
        $clean['apim_url']        = esc_url_raw( $input['apim_url'] ?? '' );
        $clean['enabled']         = empty( $input['enabled'] ) ? '0' : '1';
        $clean['greeting']        = sanitize_text_field( $input['greeting'] ?? '' );

        // Only overwrite the key if a new non-empty value was provided; never echo it.
        $submitted_key = trim( (string) ( $input['apim_subscription'] ?? '' ) );
        $clean['apim_subscription'] = '' !== $submitted_key
            ? sanitize_text_field( $submitted_key )
            : (string) ( $existing['apim_subscription'] ?? '' );

        return $clean;
    }

    public function render_page(): void {
        if ( ! current_user_can( 'manage_options' ) ) {
            return;
        }
        $opts     = get_option( COUNTY_ASSISTANT_OPT, array() );
        $has_key  = ! empty( $opts['apim_subscription'] );
        ?>
        <div class="wrap">
            <h1><?php esc_html_e( 'County Assistant Settings', 'county-assistant' ); ?></h1>
            <form method="post" action="options.php">
                <?php settings_fields( 'county_assistant_group' ); ?>
                <table class="form-table" role="presentation">
                    <tr>
                        <th scope="row"><?php esc_html_e( 'Enabled', 'county-assistant' ); ?></th>
                        <td>
                            <input type="checkbox" name="<?php echo esc_attr( COUNTY_ASSISTANT_OPT ); ?>[enabled]"
                                value="1" <?php checked( '1', $opts['enabled'] ?? '1' ); ?> />
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><?php esc_html_e( 'APIM Endpoint URL', 'county-assistant' ); ?></th>
                        <td>
                            <input type="url" class="regular-text"
                                name="<?php echo esc_attr( COUNTY_ASSISTANT_OPT ); ?>[apim_url]"
                                value="<?php echo esc_attr( $opts['apim_url'] ?? '' ); ?>"
                                placeholder="https://your-apim.azure-api.net/county-assistant/chat" />
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><?php esc_html_e( 'APIM Subscription Key', 'county-assistant' ); ?></th>
                        <td>
                            <input type="password" class="regular-text" autocomplete="new-password"
                                name="<?php echo esc_attr( COUNTY_ASSISTANT_OPT ); ?>[apim_subscription]"
                                placeholder="<?php echo $has_key ? esc_attr__( '•••••• (saved)', 'county-assistant' ) : ''; ?>" />
                            <p class="description">
                                <?php esc_html_e( 'Stored server-side only and never sent to the browser. Leave blank to keep the existing key.', 'county-assistant' ); ?>
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><?php esc_html_e( 'Greeting', 'county-assistant' ); ?></th>
                        <td>
                            <input type="text" class="regular-text"
                                name="<?php echo esc_attr( COUNTY_ASSISTANT_OPT ); ?>[greeting]"
                                value="<?php echo esc_attr( $opts['greeting'] ?? '' ); ?>" />
                        </td>
                    </tr>
                </table>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }
}
