?exists: /html/head/meta[@property="article:published_time"]
body:     //article
title:    $body//h1[1]
subtitle: $title/next-sibling::h2
$bg_section: $body//section[has-class("is-imageBackgrounded")]
@background_to_image: $bg_section//div[has-class("section-backgroundImage")]
<figure>: $bg_section//div[has-class("section-background")]
cover: $bg_section//figure
cover: $title/preceding::figure[.//img][not(has-class("is-partialWidth"))]
cover: $title/next-sibling::figure[.//img]
cover: $subtitle/next-sibling::figure[.//img]
cover: //figure[has-class("graf--layoutFillWidth")]

image_url: $cover/self::img/@src
image_url: $cover/self::figure//img/@src

image_url: //head/meta[@property="og:image"]/@content
<span>:  //blockquote[has-class("graf--pullquote")]//strong
<aside>: //blockquote[has-class("graf--pullquote")]
@inline: $body//iframe[starts-with(@src, "/media/")]
@combine(<br>,<br>): $body//pre/next-sibling::pre
@combine(<br>,<br>): $body//blockquote/next-sibling::blockquote
$embed:           $body//div[has-class("graf--mixtapeEmbed")]
@remove:          $embed//a[has-class("mixtapeImage")]
$embed_link:      $embed/a
@detach:          $embed_link/strong
@before_el(./..): $embed_link/*
@wrap(<cite>):    $embed_link
<blockquote>:     $embed

@remove: //article/header
@remove: //article/footer
@remove: $body//a[contains(@href,"/adServer.bs")]
@remove: $body//p//*[has-class("graf-dropCap")]//img[has-class("graf-dropCapImage")]

@remove: $body//section[1]//hr
@remove: $body//section[has-class("section--first")]//hr
@remove: $body//section[has-class("section--cover")]/following-sibling::*[1]/self::section//hr
@remove: $body//section[has-class("is-backgrounded")]/following-sibling::*[1]/self::section//hr

@before(<hr>): $body//figure[.//img[number(@data-height) < 30][(number(@data-width) > number(@data-height) * 30)]]
@remove

