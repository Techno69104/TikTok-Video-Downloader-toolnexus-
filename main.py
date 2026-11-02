<?php
/**
 * Tool: Best TikTok Video Downloader 2026
 */

require_once(dirname(__FILE__) . '/../header.php');

$tool_id = get_queried_object_id();
if (!$tool_id) {
    $tool_slug_current = basename(__FILE__, '.php');
    $tool_page = get_page_by_path($tool_slug_current, OBJECT, 'tool');
    $tool_id = $tool_page ? $tool_page->ID : 0;
}

$tool_title_fetched = get_the_title($tool_id);
$tool_icon_fetched = get_post_meta($tool_id, '_tool_icon', true);
if (empty($tool_icon_fetched)) $tool_icon_fetched = 'fa-brands fa-tiktok';

$usage = get_post_meta($tool_id, '_tool_usage', true);
$usage = $usage ? $usage + 1 : 1;
update_post_meta($tool_id, '_tool_usage', $usage);

function get_persistent_device_id_tool() {
    if (isset($_COOKIE['toolnexus_device_persistent'])) {
        return sanitize_text_field($_COOKIE['toolnexus_device_persistent']);
    }
    $device_id = 'device_' . time() . '_' . bin2hex(random_bytes(16));
    setcookie('toolnexus_device_persistent', $device_id, time() + (10 * 365 * 24 * 60 * 60), '/', '', false, true);
    return $device_id;
}
$persistent_device_id = get_persistent_device_id_tool();
$feedback_nonce = wp_create_nonce('toolnexus_feedback_nonce');
$ajax_url = admin_url('admin-ajax.php');

global $wpdb;
$table_name = $wpdb->prefix . 'tool_feedback';
$rating_data = $wpdb->get_row($wpdb->prepare(
    "SELECT AVG(rating) as avg_rating, COUNT(*) as total_ratings FROM $table_name WHERE tool_id = %d AND is_approved = 1",
    $tool_id
));

$primary_color = get_option('toolnexus_primary_color', '#10b981');
$primary_dark  = get_option('toolnexus_primary_dark', '#059669');
$primary_soft  = get_option('toolnexus_primary_soft', '#ecfdf5');
$border_light  = get_option('toolnexus_border_light', '#d1fae5');
$text_dark     = get_option('toolnexus_text_dark', '#0f172a');
$text_muted    = get_option('toolnexus_text_muted', '#475569');

function hex_to_rgb_tiktok($hex) {
    $hex = str_replace('#', '', $hex);
    return hexdec(substr($hex, 0, 2)) . ", " . hexdec(substr($hex, 2, 2)) . ", " . hexdec(substr($hex, 4, 2));
}
$primary_rgb = hex_to_rgb_tiktok($primary_color);
?>

<?php get_header(); ?>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

<style>
    :root { 
        --primary: <?php echo esc_attr($primary_color); ?>;
        --primary-dark: <?php echo esc_attr($primary_dark); ?>;
        --primary-soft: <?php echo esc_attr($primary_soft); ?>;
        --text-dark: <?php echo esc_attr($text_dark); ?>;
        --text-muted: <?php echo esc_attr($text_muted); ?>;
        --border-light: <?php echo esc_attr($border_light); ?>;
        --card-bg: #ffffff;
        --shadow-sm: 0 8px 20px rgba(0,0,0,0.03);
        --shadow-md: 0 12px 28px rgba(0,0,0,0.08);
    }
    
    .custom-tool-container { max-width: 1200px; margin: 0 auto; padding: 0 24px; font-family: 'Inter', sans-serif; }
    .tool-card-custom { background: var(--card-bg); border-radius: 1rem; padding: 1.5rem; margin: 20px 0; border: 1px solid var(--border-light); box-shadow: var(--shadow-sm); }
    .tool-content { line-height: 1.7; word-wrap: break-word; }
    
    .tik-card-outer { width: 100%; background: #ffffff; border: 1px solid var(--border-light); box-shadow: var(--shadow-md); border-radius: 24px; padding: 8px; margin-bottom: 2rem; }
    .tik-card-inner { background: #ffffff; border-radius: 20px; padding: 28px; overflow: hidden; }

    .tik-hero { background: linear-gradient(135deg, #0b1220 0%, #111827 40%, #1f2937 75%, #0b1220 100%); border-radius: 18px; padding: 28px 26px; margin-bottom: 24px; color: #ffffff; position: relative; box-shadow: 0 14px 34px rgba(11, 18, 32, 0.35); border: 1px solid rgba(255,255,255,0.06); }
    .tik-hero-content { position: relative; z-index: 2; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
    .tik-logo-box { width: 56px; height: 56px; border-radius: 16px; background: #ffffff; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #0b1220; box-shadow: 0 10px 22px rgba(0,0,0,0.45); flex-shrink: 0; }
    .tik-hero-text { flex: 1; min-width: 200px; }
    .tik-hero-title { font-size: 1.45rem; font-weight: 800; margin: 0 0 6px; color: #ffffff; }
    .tik-hero-sub { font-size: 0.85rem; color: rgba(255,255,255,0.72); margin: 0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-weight: 500; }
    .tik-hero-sub .dot { width: 4px; height: 4px; border-radius: 50%; background: rgba(255,255,255,0.35); display: inline-block; }
    
    .tik-feature-strip { display: flex; align-items: center; gap: 0; margin-bottom: 20px; padding: 10px 4px; background: #f8fafc; border: 1px solid var(--border-light); border-radius: 12px; }
    .tik-feature-item { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 6px 10px; font-size: 0.72rem; font-weight: 700; color: var(--text-dark); }
    .tik-feature-item i { color: var(--primary); font-size: 0.85rem; }

    .tik-input-row { display: flex; align-items: center; gap: 8px; padding: 8px; background: #fff; border: 2px solid var(--border-light); border-radius: 16px; transition: border-color 0.2s; }
    .tik-input-row:focus-within { border-color: var(--primary); box-shadow: 0 0 0 4px var(--primary-soft); }
    .tik-input-icon { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background: var(--primary-soft); border-radius: 12px; color: var(--primary); font-size: 16px; font-weight: 700; flex-shrink: 0; }
    .tik-text-input { flex: 1; min-width: 0; padding: 8px 0; border: none; outline: none; background: transparent; font-size: 15px; font-weight: 500; color: var(--text-dark); font-family: inherit; }
    .tik-paste-btn { height: 36px; padding: 0 14px; display: inline-flex; align-items: center; gap: 6px; background: #fff; border: 1px solid var(--border-light); border-radius: 10px; font-size: 12px; font-weight: 600; color: var(--text-dark); cursor: pointer; transition: all 0.15s; }
    .tik-paste-btn:hover { background: var(--primary-soft); border-color: var(--primary); color: var(--primary-dark); }

    .tik-fetch-btn { width: 100%; height: 52px; margin-top: 16px; display: flex; align-items: center; justify-content: center; gap: 10px; border: none; border-radius: 14px; font-size: 15px; font-weight: 700; color: #fff; cursor: pointer; background: linear-gradient(100deg, var(--primary) 0%, var(--primary-dark) 100%); box-shadow: 0 8px 22px rgba(<?php echo $primary_rgb; ?>, 0.22); transition: all 0.2s; }
    .tik-fetch-btn:hover:not(:disabled) { filter: brightness(1.05); box-shadow: 0 10px 28px rgba(<?php echo $primary_rgb; ?>, 0.32); }
    .tik-fetch-btn:disabled { opacity: 0.7; cursor: not-allowed; }

    .tik-spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff; border-radius: 50%; animation: tik-spin 0.8s linear infinite; }
    @keyframes tik-spin { to { transform: rotate(360deg); } }

    .tik-result-section { display: none; margin-top: 24px; }
    .tik-video-preview { display: flex; gap: 20px; background: #f8fafc; border: 1px solid var(--border-light); border-radius: 16px; padding: 16px; margin-bottom: 20px; }
    .tik-thumb-box { width: 140px; height: 180px; background: #e5e7eb; border-radius: 12px; position: relative; overflow: hidden; flex-shrink: 0; }
    .tik-thumb-box img { width: 100%; height: 100%; object-fit: cover; }
    .tik-play-icon { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 44px; height: 44px; background: rgba(255,255,255,0.9); border-radius: 50%; display: grid; place-items: center; color: #111; font-size: 16px; padding-left: 3px; }

    .tik-details { flex: 1; display: flex; flex-direction: column; justify-content: center; }
    .tik-username { font-size: 15px; font-weight: 700; color: var(--text-dark); margin-bottom: 6px; }
    .tik-caption { font-size: 13px; color: var(--text-muted); line-height: 1.4; margin-bottom: 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .tik-stats { display: flex; gap: 8px; flex-wrap: wrap; }
    .tik-pill { background: #fff; border: 1px solid var(--border-light); border-radius: 999px; padding: 4px 10px; font-size: 11px; color: var(--text-muted); font-weight: 600; }

    .tik-download-box { display: flex; flex-direction: column; padding: 20px; border: 2px solid var(--border-light); border-radius: 16px; background: #fff; }
    .tik-dl-content { display: flex; align-items: center; justify-content: space-between; width: 100%; }
    .tik-dl-left { display: flex; align-items: center; gap: 12px; }
    .tik-icon-box { width: 44px; height: 44px; background: var(--primary-soft); border-radius: 12px; display: grid; place-items: center; font-size: 18px; color: var(--primary); }
    .tik-dl-text h4 { font-size: 15px; font-weight: 700; color: var(--text-dark); margin: 0 0 4px 0; }
    .tik-dl-text span { font-size: 12px; color: var(--text-muted); }
    .tik-badge { background: var(--primary); color: #fff; font-size: 10px; padding: 2px 8px; border-radius: 999px; font-weight: 700; }
    
    .tik-dl-btn { background: var(--primary); color: #fff; border: none; border-radius: 10px; padding: 12px 28px; font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
    .tik-dl-btn:hover:not(:disabled) { background: var(--primary-dark); }
    .tik-dl-btn:disabled { opacity: 0.7; cursor: not-allowed; background: #9ca3af; }

    .tik-progress-container { display: none; width: 100%; margin-top: 16px; background: var(--primary-soft); border-radius: 8px; overflow: hidden; position: relative; height: 28px; border: 1px solid var(--border-light); }
    .tik-progress-bar { height: 100%; background: var(--primary); width: 0%; transition: width 0.2s ease; }
    .tik-progress-text { position: absolute; width: 100%; text-align: center; font-size: 12px; font-weight: 700; color: var(--text-dark); top: 50%; transform: translateY(-50%); z-index: 2; }

    @media (max-width: 600px) {
        .tik-card-inner { padding: 16px; }
        .tik-video-preview { flex-direction: column; align-items: center; text-align: center; }
        .tik-thumb-box { width: 100%; height: 220px; }
        .tik-dl-content { flex-direction: column; gap: 16px; text-align: center; }
        .tik-dl-btn { width: 100%; }
    }
    
    /* Feedback styles are kept inline for brevity, same as previous */
</style>

<main class="custom-tool-container">
    <div class="tik-card-outer">
        <div class="tik-card-inner">
            
            <div class="tik-hero">
                <div class="tik-hero-content">
                    <div class="tik-logo-box"><i class="<?php echo esc_attr($tool_icon_fetched); ?>"></i></div>
                    <div class="tik-hero-text">
                        <h1 class="tik-hero-title">TikTok Video Downloader</h1>
                        <p class="tik-hero-sub"><span><i class="fas fa-bolt"></i> Fast</span> <span class="dot"></span> <span><i class="fas fa-shield-alt"></i> Private</span> <span class="dot"></span> <span><i class="fas fa-infinity"></i> Unlimited</span></p>
                    </div>
                </div>
            </div>

            <div class="tik-feature-strip">
                <div class="tik-feature-item"><i class="fas fa-bolt"></i> Instant</div>
                <div class="tik-feature-item"><i class="fas fa-lock"></i> Private</div>
                <div class="tik-feature-item"><i class="fas fa-gem"></i> No Watermark</div>
                <div class="tik-feature-item"><i class="fas fa-infinity"></i> Unlimited</div>
            </div>

            <div class="tik-input-row">
                <div class="tik-input-icon">♪</div>
                <input type="url" id="tiktok-url" class="tik-text-input" placeholder="Paste TikTok URL here...">
                <button type="button" class="tik-paste-btn" id="paste-btn"><i class="fas fa-paste"></i> Paste</button>
            </div>

            <button type="button" class="tik-fetch-btn" id="fetch-btn">Fetch Video</button>

            <div class="tik-result-section" id="result-section">
                <div class="tik-video-preview">
                    <div class="tik-thumb-box">
                        <img src="" alt="TikTok Thumbnail" id="res-thumb">
                        <div class="tik-play-icon"><i class="fa-solid fa-play"></i></div>
                    </div>
                    <div class="tik-details">
                        <div class="tik-username" id="res-username">@username</div>
                        <div class="tik-caption" id="res-caption">Loading caption...</div>
                        <div class="tik-stats">
                            <span class="tik-pill">HD Quality</span>
                            <span class="tik-pill">No watermark</span>
                        </div>
                    </div>
                </div>

                <div class="tik-download-box">
                    <div class="tik-dl-content">
                        <div class="tik-dl-left">
                            <div class="tik-icon-box"><i class="fa-solid fa-file-video"></i></div>
                            <div class="tik-dl-text">
                                <h4>HD No Watermark (MP4) <span class="tik-badge">Best</span></h4>
                                <span>High Quality • No Watermark</span>
                            </div>
                        </div>
                        <button type="button" id="download-btn" class="tik-dl-btn">Download MP4</button>
                    </div>
                    
                    <div class="tik-progress-container" id="progress-container">
                        <div class="tik-progress-bar" id="progress-bar"></div>
                        <div class="tik-progress-text" id="progress-text">0%</div>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <!-- Content, FAQ, and Feedback sections remain unchanged from previous version -->
</main>

<script>
(function() {
    'use strict';

    var API_BASE = 'https://tiktok-video-downloader-toolnexus.onrender.com';
    var urlInput = document.getElementById('tiktok-url');
    var fetchBtn = document.getElementById('fetch-btn');
    var pasteBtn = document.getElementById('paste-btn');
    var resultSection = document.getElementById('result-section');
    var downloadBtn = document.getElementById('download-btn');
    
    var progressContainer = document.getElementById('progress-container');
    var progressBar = document.getElementById('progress-bar');
    var progressText = document.getElementById('progress-text');

    var directVideoUrl = '';

    function pasteText() {
        if (!navigator.clipboard || !navigator.clipboard.readText) {
            urlInput.focus();
            alert('Please press Ctrl+V to paste.');
            return;
        }
        urlInput.focus();
        navigator.clipboard.readText().then(function(text) {
            urlInput.value = text.trim();
        }).catch(function() {
            alert('Please press Ctrl+V to paste.');
        });
    }

    function isValidTikTokUrl(value) {
        try {
            var parsed = new URL(value);
            return (parsed.protocol === 'https:' || parsed.protocol === 'http:') &&
                (parsed.hostname === 'tiktok.com' || parsed.hostname.endsWith('.tiktok.com'));
        } catch (e) { return false; }
    }

    function fetchVideo() {
        var url = urlInput.value.trim();
        if (!isValidTikTokUrl(url)) {
            alert('Please paste a valid TikTok URL.');
            return;
        }

        fetchBtn.disabled = true;
        fetchBtn.innerHTML = '<span class="tik-spinner"></span> Fetching...';
        resultSection.style.display = 'none';
        directVideoUrl = '';

        fetch(API_BASE + '/api/info?url=' + encodeURIComponent(url), { cache: 'no-store' })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!data || data.status !== 'success' || !data.download_url) {
                    throw new Error(data.detail || 'Could not find video.');
                }

                document.getElementById('res-username').innerText = '@' + (data.author || 'user');
                document.getElementById('res-caption').innerText = data.title || 'TikTok Video';
                if (data.thumbnail) document.getElementById('res-thumb').src = data.thumbnail;

                directVideoUrl = data.download_url;
                resultSection.style.display = 'block';
            })
            .catch(function(err) {
                alert('Error: ' + err.message);
            })
            .finally(function() {
                fetchBtn.disabled = false;
                fetchBtn.innerText = 'Fetch Video';
            });
    }

    // ═══════════════════════════════════════════════════════════════
    // DIRECT BROWSER STREAMING (Bypasses Render completely!)
    // ═══════════════════════════════════════════════════════════════
    function downloadVideo() {
        if (!directVideoUrl) {
            alert('Please fetch a video first.');
            return;
        }

        var originalText = downloadBtn.innerText;
        downloadBtn.disabled = true;
        downloadBtn.innerHTML = 'Starting...';
        
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.innerText = 'Connecting to TikTok CDN...';

        var xhr = new XMLHttpRequest();
        xhr.open('GET', directVideoUrl, true);
        xhr.responseType = 'blob';

        xhr.onprogress = function(event) {
            if (event.lengthComputable) {
                var percent = Math.round((event.loaded / event.total) * 100);
                progressBar.style.width = percent + '%';
                progressText.innerText = percent + '% Downloading...';
            } else {
                progressBar.style.width = '100%';
                progressText.innerText = 'Downloading...';
            }
        };

        xhr.onload = function() {
            if (xhr.status === 200) {
                progressText.innerText = '100% - Saving File';
                var blob = xhr.response;
                var url = window.URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'tiktok_video.mp4';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                setTimeout(function() {
                    progressContainer.style.display = 'none';
                    downloadBtn.disabled = false;
                    downloadBtn.innerText = originalText;
                }, 2000);
            } else {
                handleError('Server returned status: ' + xhr.status);
            }
        };

        xhr.onerror = function() { handleError('Network error occurred.'); };

        function handleError(msg) {
            alert('Failed: ' + msg + '. The video link may have expired. Please fetch again.');
            progressContainer.style.display = 'none';
            downloadBtn.disabled = false;
            downloadBtn.innerText = originalText;
        }

        xhr.send();
    }

    fetchBtn.addEventListener('click', fetchVideo);
    pasteBtn.addEventListener('click', pasteText);
    downloadBtn.addEventListener('click', downloadVideo);
    urlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); fetchVideo(); }
    });
})();
</script>

<!-- Feedback and FAQ scripts remain the same -->
