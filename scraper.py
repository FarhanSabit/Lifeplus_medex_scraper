from langchain_medical_scraper import MedicalWebScraperAgent
import os
import time
import json

# Set your API keys 
os.environ["OPENAI_API_KEY"] = ""
os.environ["TWOCAPTCHA_API_KEY"] = ""

def scrape_medex_generics():
    # Initialize the agent with a more limited memory
    medical_scraper = MedicalWebScraperAgent()
    
    # Clear any existing memory
    medical_scraper.memory.clear()
    
    print("Starting automated web scraper with CAPTCHA solving capabilities...")
    print("The script will attempt to automatically solve any CAPTCHAs it encounters.")
    
    # Create a much more compact prompt to reduce token usage
    prompt = """
    Scrape https://medex.com.bd/generics following these EXACT steps:

    1. Fetch ONLY the first page from https://medex.com.bd/generics
    2. Use link_extractor with BOTH parameters:
    - html_content: (the HTML content)
    - base_url: "https://medex.com.bd/generics"
    3. Extract ONLY 2 medication links from the first page ONLY
    -https://medex.com.bd/generics/779/10-vitamin-6-mineral-pregnancy-and-breast-feeding-formula
    -https://medex.com.bd/generics/21/acemetacin

    4. For these 2 medication links:
    a. Scrape each page
    b. Extract EXACTLY (verbatim): name, Indications, Composition, Pharmacology, Dosage & Administration, Interaction, Contraindications, Side Effects, Pregnancy & Lactation, Precautions & Warnings, Therapeutic Class, Storage Conditions
    c. DO NOT summarize or modify the content - extract the EXACT text as it appears on the website
    5. Save as JSON to "medex_generics_data"

    IMPORTANT: Extract all data verbatim as it appears on the website with no summarization or interpretation.
    """
    
    # Execute the agent with the much smaller prompt
    try:
        result = medical_scraper.agent_executor.invoke({"input": prompt})
        return result
    except Exception as e:
        print(f"Error during scraping: {str(e)}")
        return {"error": str(e)}
    finally:
        # Add a small delay to ensure browser cleanup
        time.sleep(10)

def create_monkey_patch():
    """Create a monkey patch for the extract_links function to ensure base_url is provided"""
    from langchain_medical_scraper import extract_links as original_extract_links
    
    def patched_extract_links(html_content, base_url=None, pattern=None):
        if base_url is None:
            base_url = "https://medex.com.bd/generics"  # Default value if not provided
            print("WARNING: base_url was not provided to extract_links, using default: https://medex.com.bd/generics")
        
        # Remove the HTML truncation
        return original_extract_links(html_content, base_url, pattern)
    
    # Replace the original function with our patched version
    import langchain_medical_scraper
    langchain_medical_scraper.extract_links = patched_extract_links
    
    # Also patch the fetch_webpage function to NOT truncate HTML responses
    from langchain_medical_scraper import fetch_webpage as original_fetch_webpage
    
    def patched_fetch_webpage(url):
        result = original_fetch_webpage(url)
        # Remove the content truncation
        return result
    
    langchain_medical_scraper.fetch_webpage = patched_fetch_webpage

if __name__ == "__main__":
    print("Starting MedEx generics scraping...")
    
    # Apply the monkey patch to ensure base_url is always provided
    create_monkey_patch()
    
    result = scrape_medex_generics()
    print("\nScraping complete! Results:")
    print(result)
    
    # Check if data was successfully saved
    try:
        with open("medex_generics_data.json", "r") as f:
            data = json.load(f)
            print(f"\nSuccessfully loaded data file. Contains information on {len(data)} generic medications.")
            
            # Display a sample of the first item
            if data:
                first_item = list(data.items())[0] if isinstance(data, dict) else data[0]
                print("\nSample data from first entry:")
                print(json.dumps(first_item, indent=2)[:500] + "..." if len(json.dumps(first_item, indent=2)) > 500 else json.dumps(first_item, indent=2))
    except FileNotFoundError:
        print("\nWARNING: Data file 'medex_generics_data.json' was not found. Check if the scraping process saved the file correctly.")
    except json.JSONDecodeError:
        print("\nERROR: The data file exists but contains invalid JSON. The file might be corrupted or incomplete.")
    except Exception as e:
        print(f"\nError reading data file: {str(e)}")
    
    print("\nProcess completed.")