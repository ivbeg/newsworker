?path: /.+
$header: //header
body:    //article

@pre:    $body//*

title:          $body//h1
subtitle:       $body//h2
author:         $header//address/a[@rel="author"]
author_url:     $author/@href
published_date: $header//address/time/@datetime
@remove:        $body//address

@clone: $author_url
@match("^https?://t(elegram)?\\.me/([a-z0-9_]+)$", 2, "i"): $@
@replace(".+", "@$0")
channel

cover: $body//h1/next-sibling::figure[.//video]
cover: $body//h1/next-sibling::figure[.//img]

image_url: $cover/self::img/@src
image_url: $cover/self::figure//img/@src
image_url: /html/head/meta[@property="og:image"] \
             /@content[string()]
image_url: $body//img/@src

@before(<anchor>, name, @id): $body//h3[@id]
@before(<anchor>, name, @id): $body//h4[@id]
