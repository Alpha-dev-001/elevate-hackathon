import { NextRequest, NextResponse } from 'next/server'
import QRCode from 'qrcode'
import type { QRCampaign } from '@/types'
import { getRedisClient } from '@/lib/redis/client'

// ─── POST /api/qr/generate ────────────────────────────────────────────────────
// Generates dynamic, campaign-aware QR codes for products

export async function POST(req: NextRequest) {
  try {
    const { merchantId, productId, promoId, expiresInHours } = await req.json()

    if (!merchantId || !productId) {
      return NextResponse.json({ error: 'merchantId and productId required' }, { status: 400 })
    }

    const campaignId = `qr_${merchantId}_${productId}_${Date.now()}`
    const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000'

    // Deep link encodes the campaign context — scan data maps to active promo rules
    const deepLinkUrl = new URL(`${baseUrl}/storefront/scan`)
    deepLinkUrl.searchParams.set('c', campaignId)
    deepLinkUrl.searchParams.set('p', productId)
    deepLinkUrl.searchParams.set('m', merchantId)
    if (promoId) deepLinkUrl.searchParams.set('promo', promoId)

    const campaign: QRCampaign = {
      id: campaignId,
      productId,
      promoId,
      scanCount: 0,
      createdAt: Date.now(),
      expiresAt: expiresInHours
        ? Date.now() + expiresInHours * 3600 * 1000
        : undefined,
      deepLinkUrl: deepLinkUrl.toString(),
    }

    // Persist campaign
    const redis = getRedisClient()
    await redis.set(
      `elevate:${merchantId}:qr:${campaignId}`,
      JSON.stringify(campaign),
      ...(expiresInHours ? ['EX', expiresInHours * 3600] as const : [])
    )

    // Generate QR code as base64 data URL
    const qrDataUrl = await QRCode.toDataURL(deepLinkUrl.toString(), {
      width: 400,
      margin: 2,
      color: {
        dark: '#000000',
        light: '#FFFFFF',
      },
      errorCorrectionLevel: 'H', // High — survives damage/partial obscurity
    })

    return NextResponse.json({
      campaign,
      qrDataUrl,
      deepLinkUrl: deepLinkUrl.toString(),
    })

  } catch (error) {
    console.error('[/api/qr/generate]', error)
    return NextResponse.json(
      { error: 'QR generation failed', detail: (error as Error).message },
      { status: 500 }
    )
  }
}

// ─── GET /api/qr/generate?campaignId=&merchantId= ────────────────────────────
// Called when a QR code is scanned — records scan, returns active promo

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const campaignId = searchParams.get('c')
  const merchantId = searchParams.get('m')

  if (!campaignId || !merchantId) {
    return NextResponse.json({ error: 'Campaign and merchant ID required' }, { status: 400 })
  }

  const redis = getRedisClient()
  const raw = await redis.get(`elevate:${merchantId}:qr:${campaignId}`)

  if (!raw) {
    return NextResponse.json({ error: 'Campaign not found or expired' }, { status: 404 })
  }

  const campaign: QRCampaign = JSON.parse(raw)

  // Increment scan count
  campaign.scanCount += 1
  await redis.set(
    `elevate:${merchantId}:qr:${campaignId}`,
    JSON.stringify(campaign)
  )

  return NextResponse.json({ campaign })
}
