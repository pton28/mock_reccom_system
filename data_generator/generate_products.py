import random

CATEGORIES = ["Laptops", "Phones", "Tablets", "Headphones", "Keyboards", "Mice", "Monitors", "Cameras", "Speakers", "Wearables"]
BRANDS = [f"B{i:02d}" for i in range(1, 21)]
BRAND_NAMES = ["Nova", "Orbit", "Pulse", "Vertex", "Forma", "Pixel", "Aero", "Nexus", "Halo", "Flux", "Kova", "Luma", "Echo", "Onyx", "Zen", "Prism", "Volt", "Arc", "Modo", "Axis"]


def generate_products(count=300, seed=42):
    rng = random.Random(seed)
    products = []
    for i in range(count):
        category = CATEGORIES[i % len(CATEGORIES)]
        series = f"Series {i + 1:03d}"
        brand = rng.randrange(20)
        price = rng.randrange(40, 220) * (10 if category == "Laptops" else 3 if category in {"Phones", "Cameras", "Monitors"} else 1)
        specs_by_category = {
            'Laptops': {'cpu': rng.choice(['Intel Core i5-1340P', 'AMD Ryzen 7 7840U']), 'ram_gb': rng.choice([8,16,32]), 'storage_gb': rng.choice([256,512,1024]), 'display_inches': rng.choice([13.3,14,15.6]), 'battery_wh': rng.choice([45,60,75])},
            'Phones': {'chipset': rng.choice(['Snapdragon 8 Gen 2','Dimensity 8200']), 'ram_gb': rng.choice([6,8,12]), 'storage_gb': rng.choice([128,256,512]), 'display_inches': rng.choice([6.1,6.5,6.7]), 'battery_mah': rng.choice([4000,4500,5000]), 'camera_mp': rng.choice([48,50,108])},
            'Tablets': {'ram_gb': rng.choice([4,8,12]), 'storage_gb': rng.choice([64,128,256]), 'display_inches': rng.choice([10.1,11,12.9]), 'battery_mah': rng.choice([7000,8000,10000])},
            'Headphones': {'driver_mm': rng.choice([30,40,50]), 'anc': rng.choice([True,False]), 'battery_hours': rng.choice([20,30,40]), 'bluetooth_version': '5.3'},
            'Keyboards': {'switch_type': rng.choice(['mechanical linear','mechanical tactile','membrane']), 'key_count': rng.choice([68,87,104]), 'connection': rng.choice(['USB-C','Bluetooth / USB-C'])},
            'Mice': {'sensor_dpi': rng.choice([8000,16000,26000]), 'weight_g': rng.choice([58,72,90]), 'button_count': rng.choice([5,6,8]), 'connection': rng.choice(['USB','2.4 GHz wireless'])},
            'Monitors': {'display_inches': rng.choice([24,27,32]), 'resolution': rng.choice(['1920x1080','2560x1440','3840x2160']), 'refresh_hz': rng.choice([60,120,144]), 'panel': rng.choice(['IPS','VA','OLED'])},
            'Cameras': {'sensor': rng.choice(['APS-C','Full frame']), 'resolution_mp': rng.choice([24,32,45]), 'video': rng.choice(['4K 30 fps','4K 60 fps']), 'lens_mount': 'Demo mount'},
            'Speakers': {'power_w': rng.choice([10,20,40]), 'battery_hours': rng.choice([8,12,20]), 'bluetooth_version': '5.3', 'water_resistance': rng.choice(['IPX4','IPX7'])},
            'Wearables': {'display_inches': rng.choice([1.4,1.6,1.8]), 'battery_days': rng.choice([3,7,14]), 'gps': rng.choice([True,False]), 'water_resistance': '5 ATM'},
        }
        technical = specs_by_category[category]
        products.append({"id": f"P{i + 1:04d}", "name": f"{BRAND_NAMES[brand]} {series} {category.rstrip('s')} {i + 1}",
                         "category_id": category.lower(), "category": category, "brand_id": BRANDS[brand],
                         "brand": BRAND_NAMES[brand], "price": price, "stock": rng.randint(0, 35),
                         "color": ["mint", "lavender", "sand", "blue"][i % 4],
                         "description": f"{BRAND_NAMES[brand]} {category.lower().rstrip('s')}, model {i + 1:03d}. Synthetic specifications for demonstration; 24-month demo warranty.",
                         "attributes": {"series": series, "warranty_months": 24, **technical}})
    for product in products:
        product['variants'] = [{'sku': f"SKU-{product['id']}", 'price': product['price'], 'quantity': product['stock']}]
        product['specifications'] = [{'specification_name': k, 'specification_value': str(v)} for k, v in product['attributes'].items()]
        product['avg_rating'] = None
        product['sold_count'] = 0
        product['is_published'] = True
    return products
