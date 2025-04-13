import os
import time
import json
import random
from bs4 import BeautifulSoup
import requests
import re

# Set your API keys (consider using environment variables instead of hardcoding)
os.environ["OPENAI_API_KEY"] = "YOUR_OPENAI_API_KEY"
os.environ["TWOCAPTCHA_API_KEY"] = "e7c5e0c9f1040e8838aecdd856176216"

def debug_page_structure(url):
    """Debug function to investigate the page structure"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    try:
        response = requests.get(url, headers=headers)
        
        # Print response status and headers
        print(f"Response status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        
        # Check if it might be a JavaScript-rendered page
        if "text/html" in response.headers.get('Content-Type', ''):
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Save the HTML for inspection
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print(f"Saved HTML to debug_page.html")
            
            # Check for common elements
            print("\nPage Structure Analysis:")
            print(f"Title: {soup.title.text if soup.title else 'No title found'}")
            
            # Look for tables
            tables = soup.find_all('table')
            print(f"Number of tables found: {len(tables)}")
            
            # Look for possible medicine containers
            data_rows = soup.select('tr.data-row')
            print(f"Data rows found: {len(data_rows)}")
            
            data_rows_alt = soup.select('.data-row')
            print(f"Alternative data rows found: {len(data_rows_alt)}")
            
            # Look for any links containing "/brands/"
            brand_links = [a['href'] for a in soup.find_all('a') if a.has_attr('href') and '/brands/' in a['href']]
            print(f"brand links found: {len(brand_links)}")
            if brand_links:
                print("Sample links:")
                for link in brand_links[:5]:
                    print(f"  - {link}")
            
            # Check if there's pagination
            pagination = soup.select('.pagination')
            print(f"Pagination elements found: {len(pagination)}")
            
            # Look for JavaScript that might be rendering content
            scripts = soup.find_all('script')
            print(f"Script tags found: {len(scripts)}")
            
            return soup
        else:
            print("Response is not HTML. Cannot analyze structure.")
            return None
    except Exception as e:
        print(f"Error during debug: {str(e)}")
        return None

def extract_links_from_page(page_url):
    """Extract medication links from a page using optimized selectors"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        response = requests.get(page_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Print debugging information
        print(f"Page title: {soup.title.text if soup.title else 'No title found'}")
        
        # Save the HTML content for inspection
        with open(f"page_debug_{page_url.split('=')[-1]}.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        
        links = []
        
        # Try multiple selectors to find medication links
        # Method 1: Look for direct links containing /brands/
        for a_tag in soup.find_all('a'):
            if a_tag.has_attr('href') and '/brands/' in a_tag['href']:
                href = a_tag['href']
                # Make sure it's a full URL
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = f"https://medex.com.bd{href}"
                if full_url not in links:
                    links.append(full_url)
        
        # Method 2: Try to find links in table rows
        for row in soup.select('tr'):
            for a_tag in row.find_all('a'):
                if a_tag.has_attr('href') and '/brands/' in a_tag['href']:
                    href = a_tag['href']
                    # Make sure it's a full URL
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://medex.com.bd{href}"
                    if full_url not in links:
                        links.append(full_url)
        
        # Method 3: Try to find links in any div with class containing 'data'
        for div in soup.select('div[class*="data"]'):
            for a_tag in div.find_all('a'):
                if a_tag.has_attr('href') and '/brands/' in a_tag['href']:
                    href = a_tag['href']
                    # Make sure it's a full URL
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://medex.com.bd{href}"
                    if full_url not in links:
                        links.append(full_url)
        
        if not links:
            print("WARNING: No links found with any of the selectors.")
            print("Attempting to extract links using regular expressions...")
            
            # Try using regex to find all URLs containing 'brands'
            brand_urls = re.findall(r'href=[\'"]?([^\'" >]+/brands/[^\'" >]+)', response.text)
            for url in brand_urls:
                # Clean up the URL
                url = url.replace('href="', '').replace("href='", '')
                # Make sure it's a full URL
                if url.startswith('http'):
                    full_url = url
                else:
                    full_url = f"https://medex.com.bd{url}"
                if full_url not in links:
                    links.append(full_url)
        
        # Print the found links for debugging
        if links:
            print("Found links:")
            for link in links[:5]:
                print(f"  - {link}")
            if len(links) > 5:
                print(f"  ... and {len(links) - 5} more")
        else:
            print("No links found even with regex approach.")
        
        return links
        
    except Exception as e:
        print(f"Error extracting links from {page_url}: {str(e)}")
        return []

def scrape_medicine_details(url):
    """Scrape details for a specific medicine URL using BeautifulSoup"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract medication details
        med_data = {}
        
        # Extract name
        name_elem = soup.select_one('.drug-header-name h1, h1.drug-name, h1')
        if name_elem:
            med_data['name'] = name_elem.text.strip()
        else:
            med_data['name'] = "Unknown"
        
        # Extract pack image URL (from the <a> tag with the "pack image" link)
        pack_image_elem = soup.select_one('a.innovator-brand-badge')  # Selector for pack image link
        if pack_image_elem and pack_image_elem.has_attr('href'):
            med_data['pack_image_url'] = pack_image_elem['href']
        else:
            med_data['pack_image_url'] = "Not available"
        
        # Extract Strength (from the <div title="Strength">)
        strength_elem = soup.select_one('div[title="Strength"]')
        if strength_elem:
            med_data['strength'] = strength_elem.text.strip()
        else:
            med_data['strength'] = "Not available"
        
        # Extract Manufacturer (from the <div title="Manufactured by">)
        manufacturer_elem = soup.select_one('div[title="Manufactured by"] a')
        if manufacturer_elem:
            med_data['manufacturer'] = manufacturer_elem.text.strip()
        else:
            med_data['manufacturer'] = "Not available"
        
        # Extract price information - NEW APPROACH FOR MULTIPLE PACKAGE TYPES
        price_data = []
        package_containers = soup.select('div.package-container')
        
        if package_containers:
            for container in package_containers:
                package_info = {}
                
                # Extract package type (e.g., "3 ml biopen", "3 ml cartridge")
                package_type_elem = container.select_one('span[style="color: #3a5571;"]')
                if package_type_elem:
                    package_info['package_type'] = package_type_elem.text.strip()
                
                # Extract unit price
                price_elem = package_type_elem.find_next('span') if package_type_elem else None
                if price_elem:
                    package_info['unit_price'] = price_elem.text.strip()
                
                # Extract pack size info
                pack_size_elem = container.select_one('.pack-size-info')
                if pack_size_elem:
                    package_info['pack_size_info'] = pack_size_elem.text.strip()
                
                # Add to price data if we have at least a package type and price
                if 'package_type' in package_info and 'unit_price' in package_info:
                    price_data.append(package_info)
        
        # Add price data to med_data
        if price_data:
            med_data['price_data'] = price_data
        else:
            # Fall back to the old method if no package containers are found
            unit_price_elem = soup.select_one('div.package-container span[style="color: #3a5571;"]:-soup-contains("Unit Price:") + span')
            if unit_price_elem:
                med_data['unit_price'] = unit_price_elem.text.strip()
            else:
                med_data['unit_price'] = "Not available"
            
            pack_size_info_elem = soup.select_one('span.pack-size-info')
            if pack_size_info_elem:
                med_data['pack_size_info'] = pack_size_info_elem.text.strip()
            else:
                med_data['pack_size_info'] = "Not available"
        
        # Extract brand ID from URL
        brand_id_match = re.search(r'/brands/(\d+)/', url)
        if brand_id_match:
            med_data['brand_id'] = brand_id_match.group(1)
        
        # Collect all heading elements (e.g., h1, h2, h3, h4) to find sections
        all_headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'strong', '.section-title'])
        
        # Extract all sections
        sections = [
            'Indications', 'Composition', 'Pharmacology', 'Dosage & Administration', 
            'Interaction', 'Contraindications', 'Side Effects', 'Pregnancy & Lactation', 
            'Precautions & Warnings', 'Therapeutic Class', 'Storage Conditions',
            'Manufactured by', 'Common Questions'
        ]
        
        details_container = soup.select_one('.drug-details, #drug-details, .medicine-details')
        
        for section in sections:
            section_content = "Not available"
            
            # Try to find the section by different strategies
            section_id = section.lower().replace(' & ', '-').replace(' ', '-')
            section_elem = soup.select_one(f'#{section_id}, .{section_id}')
            
            if not section_elem:
                for heading in all_headings:
                    if section.lower() in heading.text.strip().lower():
                        section_elem = heading
                        break
            
            if section_elem:
                # Try to get the content
                next_elem = section_elem.find_next_sibling(['div', 'p', 'span'])
                if next_elem:
                    section_content = next_elem.text.strip()
                
                if section_content == "Not available" and section_elem.parent:
                    next_elem = section_elem.parent.find_next_sibling(['div', 'p', 'span'])
                    if next_elem:
                        section_content = next_elem.text.strip()
                
                # Collect data
                med_data[section] = section_content
        
        return med_data
        
    except Exception as e:
        print(f"Error scraping details for {url}: {str(e)}")
        return {"name": "Error", "error": str(e)}

def get_total_pages():
    """Get the total number of pages from the pagination"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        response = requests.get("https://medex.com.bd/brands", headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find pagination with multiple approaches
        # Approach 1: Standard pagination class
        pagination = soup.select('.pagination li')
        if pagination:
            # Try to get the last page number
            try:
                last_page = int(pagination[-2].text.strip())
                return last_page
            except:
                pass
        
        # Approach 2: Try to find any element that looks like pagination
        page_links = []
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if 'page=' in href:
                page_num_match = re.search(r'page=(\d+)', href)
                if page_num_match:
                    page_links.append(int(page_num_match.group(1)))
        
        if page_links:
            return max(page_links)
        
        # Default if we can't determine
        return 82  # We know there are 82 pages from your previous run
    except Exception as e:
        print(f"Error determining page count: {str(e)}")
        return 82  # Default based on your previous run

def analyze_site():
    """Run a comprehensive analysis of the site structure"""
    print("Running site analysis...")
    
    # Analyze main page
    print("\n=== Analyzing main page ===")
    soup = debug_page_structure("https://medex.com.bd/brands")
    
    # Analyze a specific medicine page
    print("\n=== Analyzing a specific medicine page ===")
    debug_page_structure("https://medex.com.bd/brands/779/10-vitamin-6-mineral-pregnancy-and-breast-feeding-formula")
    
    # Analyze the second page of results
    print("\n=== Analyzing second page ===")
    debug_page_structure("https://medex.com.bd/brands?page=2")
    
    print("\nAnalysis complete. Check the debug HTML files for more information.")

def scrape_medex_brands_full(max_pages=None, start_page=1):
    """Scrape all brands from MedEx with improved debugging"""
    
    all_data = {}
    
    # Get the total number of pages
    total_pages = get_total_pages()
    print(f"Total pages found: {total_pages}")
    
    # Apply the max_pages limit if specified
    if max_pages is not None and max_pages > 0:
        end_page = min(start_page + max_pages - 1, total_pages)
    else:
        end_page = total_pages
    
    # Process each page
    for page_num in range(start_page, end_page + 1):
        print(f"Processing page {page_num}/{end_page}...")
        
        # Get the page URL
        page_url = f"https://medex.com.bd/brands?page={page_num}"
        
        # Extract links from the page
        links = extract_links_from_page(page_url)
        print(f"Found {len(links)} medicines on page {page_num}")
        
        if not links:
            print("No links found on this page. Continuing to next page...")
            continue
        
        # Process each link
        for i, link in enumerate(links):
            print(f"Processing medicine {i+1}/{len(links)} on page {page_num}: {link}")
            
            # Scrape medicine details
            med_data = scrape_medicine_details(link)
            
            # Add to the data collection
            all_data[link] = med_data
            
            # Save incrementally after each medicine
            with open("medex_brands_data.json", "w") as f:
                json.dump(all_data, f, indent=2)
            
            # Add a small random delay to be respectful
            time.sleep(random.uniform(2, 5))
        
        # Add delay between pages
        time.sleep(random.uniform(5, 10))
    
    print(f"Completed processing {len(all_data)} medicines across {end_page - start_page + 1} pages.")
    return all_data

if __name__ == "__main__":
    print("Starting MedEx brands scraping...")
    
    # Choose which function to run
    print("Choose scraping mode:")
    print("1: Analyze site structure (debug)")
    print("2: Full scrape (all medications)")
    print("3: Scrape specific page range")
    print("4: Scrape test URLs")
    
    scrape_mode = input("Enter your choice (1-4): ")
    
    if scrape_mode == "1":
        print("Running site analysis...")
        analyze_site()
    elif scrape_mode == "2":
        print("Running full scrape with no limitations...")
        result = scrape_medex_brands_full()
    elif scrape_mode == "3":
        start_page = int(input("Enter start page number: "))
        max_pages = int(input("Enter number of pages to scrape: "))
        print(f"Scraping from page {start_page} for {max_pages} pages...")
        result = scrape_medex_brands_full(max_pages=max_pages, start_page=start_page)
    elif scrape_mode == "4":
        print("Testing with known URLs...")
        test_urls = [
            "https://medex.com.bd/brands/779/10-vitamin-6-mineral-pregnancy-and-breast-feeding-formula",
            "https://medex.com.bd/brands/21/acemetacin"
        ]
        all_data = {}
        for url in test_urls:
            print(f"Processing {url}")
            med_data = scrape_medicine_details(url)
            all_data[url] = med_data
        
        with open("medex_test_data.json", "w") as f:
            json.dump(all_data, f, indent=2)
    else:
        print("Invalid choice. Running site analysis...")
        analyze_site()
    
    print("\nProcess completed.")