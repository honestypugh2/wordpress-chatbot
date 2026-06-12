<?php
/**
 * County of Westvale (Demo) theme bootstrap.
 *
 * Minimal classic theme that renders the synthetic county portal homepage and
 * loads the theme stylesheet. The County Assistant plugin injects the chat
 * widget via wp_footer, so this theme only needs to call wp_head()/wp_footer().
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

function county_westvale_setup(): void {
    add_theme_support( 'title-tag' );
    add_theme_support( 'automatic-feed-links' );
}
add_action( 'after_setup_theme', 'county_westvale_setup' );

function county_westvale_assets(): void {
    wp_enqueue_style(
        'county-westvale',
        get_stylesheet_uri(),
        array(),
        '0.1.0'
    );
}
add_action( 'wp_enqueue_scripts', 'county_westvale_assets' );
