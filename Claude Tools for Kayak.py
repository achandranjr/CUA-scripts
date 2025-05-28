#!/usr/bin/env python3
"""
This script uses Claude's web tools to search Kayak.com for flights
"""

import anthropic
import json
import re
from datetime import datetime
from typing import Dict, List, Any

class KayakClaudeSearcher:
    def __init__(self, api_key: str = None):
        """Initialize with Anthropic API key."""
        self.api_key = api_key or self._get_api_key()
        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY or pass directly.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
        # Define Kayak-specific tools for Claude
        self.tools = [
            {
                "name": "search_kayak_flights",
                "description": "Search for flights specifically on Kayak.com",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string", "description": "Origin airport code or city"},
                        "destination": {"type": "string", "description": "Destination airport code or city"},
                        "departure_date": {"type": "string", "description": "Departure date (YYYY-MM-DD)"},
                        "return_date": {"type": "string", "description": "Return date (YYYY-MM-DD)"},
                        "passengers": {"type": "integer", "description": "Number of passengers", "default": 1}
                    },
                    "required": ["origin", "destination", "departure_date", "return_date"]
                }
            },
            {
                "name": "fetch_kayak_details",
                "description": "Fetch detailed flight information from a Kayak URL",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Kayak URL to fetch flight details from"},
                        "search_params": {"type": "object", "description": "Search parameters for context"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "analyze_kayak_results",
                "description": "Analyze and compare Kayak flight results",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "flight_data": {"type": "array", "description": "Array of flight data from Kayak"},
                        "preferences": {"type": "string", "description": "User preferences for analysis"}
                    },
                    "required": ["flight_data"]
                }
            }
        ]

    def _get_api_key(self):
        """Get API key from environment or user input."""
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            print("No API key found in environment.")
            api_key = input("Enter your Anthropic API key: ").strip()
        return api_key

    def search_kayak_flights(self, origin: str, destination: str, departure_date: str, 
                           return_date: str, passengers: int = 1) -> Dict[str, Any]:
        """Search for flights specifically on Kayak."""
        try:
            print(f"Searching Kayak for flights from {origin} to {destination}")
            print(f"Departure: {departure_date}, Return: {return_date}, Passengers: {passengers}")
            
            # Build Kayak-specific search query
            kayak_query = self._build_kayak_query(origin, destination, departure_date, return_date, passengers)
            
            # Search prompt focused on Kayak
            search_prompt = f"""
            Search specifically on Kayak.com for round-trip flights with these parameters:
            - Origin: {origin}
            - Destination: {destination}
            - Departure Date: {departure_date}
            - Return Date: {return_date}
            - Passengers: {passengers}
            
            Find current flight options on Kayak and extract:
            1. Flight prices (total roundtrip cost)
            2. Airline names
            3. Departure and arrival times for both outbound and return flights
            4. Flight duration
            5. Number of stops (nonstop, 1 stop, 2+ stops)
            6. Aircraft type if available
            
            Search query: {kayak_query}
            
            Focus only on results from kayak.com and provide detailed flight information.
            """
            
            # Perform the web search using Claude's capabilities
            search_result = self._perform_kayak_search(search_prompt)
            
            if search_result.get("success"):
                return {
                    "success": True,
                    "source": "Kayak",
                    "flights": search_result["flights"],
                    "url": search_result.get("url", ""),
                    "search_params": {
                        "origin": origin,
                        "destination": destination,
                        "departure_date": departure_date,
                        "return_date": return_date,
                        "passengers": passengers
                    },
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": search_result.get("error", "Search failed")
                }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Kayak search failed: {str(e)}"
            }

    def _build_kayak_query(self, origin: str, destination: str, departure_date: str, 
                          return_date: str, passengers: int) -> str:
        """Build Kayak-specific search query."""
        
        # Format dates for search
        dep_formatted = departure_date.replace('-', '/')
        ret_formatted = return_date.replace('-', '/')
        
        # Build comprehensive Kayak search query
        query = f"site:kayak.com flights {origin} to {destination} {dep_formatted} return {ret_formatted}"
        
        if passengers > 1:
            query += f" {passengers} passengers"
        
        # Add additional Kayak-specific terms
        query += " roundtrip airfare prices booking"
        
        return query

    def _perform_kayak_search(self, search_prompt: str) -> Dict[str, Any]:
        """Perform Kayak search using Claude's web capabilities."""
        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": search_prompt
                    }
                ]
            )
            
            # Extract search results
            search_content = ""
            for content_block in response.content:
                if content_block.type == "text":
                    search_content += content_block.text
            
            # Parse Kayak flight information
            flights = self._parse_kayak_flights(search_content)
            
            # Try to extract Kayak URL if mentioned
            kayak_url = self._extract_kayak_url(search_content)
            
            return {
                "success": True,
                "flights": flights,
                "url": kayak_url,
                "raw_content": search_content
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _parse_kayak_flights(self, content: str) -> List[Dict[str, Any]]:
        """Parse flight information specifically from Kayak search results."""
        flights = []
        
        try:
            # Extract prices (Kayak typically shows total roundtrip prices)
            price_patterns = [
                r'\$[\d,]+(?:\.\d{2})?',  # Standard price format
                r'[\d,]+\s*dollars?',     # Written dollar amounts
                r'USD\s*[\d,]+',          # USD format
            ]
            
            prices = []
            for pattern in price_patterns:
                prices.extend(re.findall(pattern, content, re.IGNORECASE))
            
            # Clean and deduplicate prices
            cleaned_prices = []
            for price in prices:
                if '$' in price:
                    cleaned_prices.append(price)
                elif 'dollar' in price.lower():
                    amount = re.search(r'[\d,]+', price)
                    if amount:
                        cleaned_prices.append(f"${amount.group()}")
                elif 'USD' in price:
                    amount = re.search(r'[\d,]+', price)
                    if amount:
                        cleaned_prices.append(f"${amount.group()}")
            
            # Remove duplicates while preserving order
            unique_prices = []
            for price in cleaned_prices:
                if price not in unique_prices:
                    unique_prices.append(price)
            
            # Extract flight times
            time_pattern = r'\b\d{1,2}:\d{2}\s*(?:AM|PM)\b'
            times = re.findall(time_pattern, content, re.IGNORECASE)
            
            # Extract airlines (common ones that appear on Kayak)
            airlines = [
                'American Airlines', 'American', 'Delta', 'Delta Air Lines', 
                'United', 'United Airlines', 'Southwest', 'JetBlue', 'Alaska',
                'Alaska Airlines', 'Spirit', 'Frontier', 'Allegiant', 'Hawaiian',
                'Air Canada', 'Lufthansa', 'British Airways', 'KLM', 'Air France'
            ]
            
            found_airlines = []
            content_lower = content.lower()
            for airline in airlines:
                if airline.lower() in content_lower:
                    # Use shorter name if both versions found
                    short_name = airline.split()[0] if ' ' in airline else airline
                    if short_name not in found_airlines:
                        found_airlines.append(short_name)
            
            # Extract durations
            duration_patterns = [
                r'\b\d+h\s*\d*m?\b',      # 2h 30m format
                r'\b\d+\s*hours?\s*\d*\s*minutes?\b',  # 2 hours 30 minutes
                r'\b\d+:\d+\b'            # 2:30 format
            ]
            
            durations = []
            for pattern in duration_patterns:
                durations.extend(re.findall(pattern, content, re.IGNORECASE))
            
            # Extract stop information
            stop_patterns = [
                r'nonstop', r'non-stop', r'direct',
                r'1 stop', r'one stop', r'1-stop',
                r'2 stops?', r'two stops?', r'2-stops?',
                r'\d+\s*stops?'
            ]
            
            stops_info = []
            for pattern in stop_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                stops_info.extend(matches)
            
            # Create flight objects
            max_flights = max(len(unique_prices), len(found_airlines), len(durations), 1)
            max_flights = min(max_flights, 15)  # Limit to 15 flights
            
            for i in range(max_flights):
                flight = {
                    "index": i + 1,
                    "source": "Kayak"
                }
                
                # Assign data with bounds checking
                if i < len(unique_prices):
                    flight["price"] = unique_prices[i]
                
                if i < len(found_airlines):
                    flight["airline"] = found_airlines[i]
                
                if i < len(durations):
                    flight["duration"] = durations[i]
                
                # Assign times (assuming pairs for outbound/return)
                if i * 4 < len(times):
                    flight["outbound_departure"] = times[i * 4] if i * 4 < len(times) else None
                    flight["outbound_arrival"] = times[i * 4 + 1] if i * 4 + 1 < len(times) else None
                    flight["return_departure"] = times[i * 4 + 2] if i * 4 + 2 < len(times) else None
                    flight["return_arrival"] = times[i * 4 + 3] if i * 4 + 3 < len(times) else None
                elif i * 2 < len(times):
                    flight["departure_time"] = times[i * 2]
                    flight["arrival_time"] = times[i * 2 + 1] if i * 2 + 1 < len(times) else None
                
                if i < len(stops_info):
                    flight["stops"] = stops_info[i]
                
                # Only add flight if it has meaningful data
                if any(key in flight for key in ['price', 'airline', 'duration', 'departure_time']):
                    flights.append(flight)
            
            # If we didn't find structured data, try to extract from paragraphs
            if not flights:
                flights = self._extract_flights_from_paragraphs(content)
            
        except Exception as e:
            print(f"Error parsing Kayak flights: {e}")
        
        return flights

    def _extract_flights_from_paragraphs(self, content: str) -> List[Dict[str, Any]]:
        """Extract flight data from paragraph-style content."""
        flights = []
        
        # Split content into paragraphs
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        for i, paragraph in enumerate(paragraphs[:10]):
            if any(keyword in paragraph.lower() for keyword in ['flight', 'price', '$', 'airline', 'depart']):
                flight = {
                    "index": len(flights) + 1,
                    "source": "Kayak",
                    "description": paragraph[:200] + "..." if len(paragraph) > 200 else paragraph
                }
                
                # Extract price from paragraph
                price_match = re.search(r'\$[\d,]+(?:\.\d{2})?', paragraph)
                if price_match:
                    flight["price"] = price_match.group()
                
                # Extract times from paragraph
                time_matches = re.findall(r'\b\d{1,2}:\d{2}\s*(?:AM|PM)\b', paragraph, re.IGNORECASE)
                if time_matches:
                    flight["times"] = time_matches
                
                flights.append(flight)
        
        return flights

    def _extract_kayak_url(self, content: str) -> str:
        """Extract Kayak URL from search results."""
        url_patterns = [
            r'https?://(?:www\.)?kayak\.com[^\s\)]*',
            r'kayak\.com/flights[^\s\)]*'
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group()
        
        return ""

    def fetch_kayak_details(self, url: str, search_params: Dict = None) -> Dict[str, Any]:
        """Fetch detailed flight information from a Kayak URL."""
        try:
            fetch_prompt = f"""
            Please fetch and analyze the flight information from this Kayak URL: {url}
            
            Extract detailed flight information including:
            1. All available flight options with exact prices
            2. Complete flight schedules (departure/arrival times)
            3. Airline names and flight numbers
            4. Aircraft types
            5. Duration and layover information
            6. Baggage fees and policies
            7. Seat selection options
            8. Booking class information (Basic Economy, Main Cabin, etc.)
            
            Provide a comprehensive summary of all flight options available on this Kayak page.
            """
            
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": fetch_prompt
                    }
                ]
            )
            
            content = ""
            for content_block in response.content:
                if content_block.type == "text":
                    content += content_block.text
            
            # Parse the detailed flight information
            detailed_flights = self._parse_detailed_kayak_data(content)
            
            return {
                "success": True,
                "url": url,
                "flights": detailed_flights,
                "raw_content": content,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch Kayak details: {str(e)}",
                "url": url
            }

    def _parse_detailed_kayak_data(self, content: str) -> List[Dict[str, Any]]:
        """Parse detailed flight information from Kayak."""
        flights = []
        
        # Split content into sections that might represent different flights
        sections = content.split('\n\n')
        
        for i, section in enumerate(sections):
            if any(keyword in section.lower() for keyword in ['flight', 'price', 'airline', 'departure', '$']):
                flight = {
                    "index": i + 1,
                    "source": "Kayak Detailed",
                    "full_details": section.strip()
                }
                
                # Extract specific information using regex
                price_match = re.search(r'\$[\d,]+(?:\.\d{2})?', section)
                if price_match:
                    flight["price"] = price_match.group()
                
                # Extract flight numbers
                flight_num_match = re.search(r'(?:Flight|FL)\s*([A-Z]{2}\d+)', section, re.IGNORECASE)
                if flight_num_match:
                    flight["flight_number"] = flight_num_match.group(1)
                
                # Extract times
                time_matches = re.findall(r'\b\d{1,2}:\d{2}\s*(?:AM|PM)\b', section, re.IGNORECASE)
                if time_matches:
                    flight["times"] = time_matches
                
                # Extract duration
                duration_match = re.search(r'\b\d+h\s*\d*m?\b', section)
                if duration_match:
                    flight["duration"] = duration_match.group()
                
                flights.append(flight)
        
        return flights[:15]  # Limit to 15 detailed flights

    def search_flights_with_claude(self, origin: str, destination: str, departure_date: str, 
                                 return_date: str, passengers: int = 1) -> str:
        """Main function to search Kayak flights using Claude."""
        
        prompt = f"""Please search for round-trip flights specifically on Kayak.com and provide a detailed analysis.

Flight Search Parameters:
- Origin: {origin}
- Destination: {destination}
- Departure Date: {departure_date}
- Return Date: {return_date}
- Passengers: {passengers}

Please search only Kayak.com and provide:
1. Current flight options available on Kayak
2. Price range and best deals
3. Airline options and their offerings
4. Flight schedules and durations
5. Recommendations for booking
6. Any special deals or promotions on Kayak

Focus exclusively on Kayak results and ignore other travel booking sites.
"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                tools=self.tools,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            result = ""
            
            for content_block in response.content:
                if content_block.type == "text":
                    result += content_block.text
                elif content_block.type == "tool_use":
                    # Handle tool calls
                    tool_result = self._handle_tool_call(content_block.name, content_block.input)
                    
                    # Continue conversation with tool result
                    follow_up = self.client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=4000,
                        messages=[
                            {
                                "role": "user",
                                "content": prompt
                            },
                            {
                                "role": "assistant",
                                "content": response.content
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": content_block.id,
                                        "content": json.dumps(tool_result)
                                    }
                                ]
                            }
                        ],
                        tools=self.tools
                    )
                    
                    # Get the final analysis
                    for block in follow_up.content:
                        if block.type == "text":
                            result += block.text
            
            return result
            
        except Exception as e:
            return f"Error: Failed to search Kayak flights - {str(e)}"

    def _handle_tool_call(self, tool_name: str, tool_input: Dict) -> Dict:
        """Handle tool calls from Claude."""
        if tool_name == "search_kayak_flights":
            return self.search_kayak_flights(**tool_input)
        elif tool_name == "fetch_kayak_details":
            return self.fetch_kayak_details(**tool_input)
        elif tool_name == "analyze_kayak_results":
            return {"analysis": "Kayak analysis completed", "data": tool_input.get("flight_data", [])}
        else:
            return {"error": f"Unknown tool: {tool_name}"}

def main():
    """Main function for Kayak-only flight search."""
    print("Kayak Flight Search with Claude")
    print("=" * 40)
    print("This searches only Kayak.com for flight information")
    print("-" * 40)
    
    # Get API key
    api_key = input("Enter your Anthropic API key: ").strip()
    if not api_key:
        print("API key required")
        return
    
    try:
        searcher = KayakClaudeSearcher(api_key=api_key)
    except ValueError as e:
        print(f"Error: {e}")
        return
    
    # Get search parameters
    origin = input("Origin airport/city: ").strip()
    destination = input("Destination airport/city: ").strip()
    
    # Validate dates
    while True:
        try:
            departure = input("Departure date (YYYY-MM-DD): ").strip()
            datetime.strptime(departure, "%Y-%m-%d")
            break
        except ValueError:
            print("Invalid format. Use YYYY-MM-DD")
    
    while True:
        try:
            return_date = input("Return date (YYYY-MM-DD): ").strip()
            datetime.strptime(return_date, "%Y-%m-%d")
            break
        except ValueError:
            print("Invalid format. Use YYYY-MM-DD")
    
    passengers = input("Passengers (default 1): ").strip()
    passengers = int(passengers) if passengers.isdigit() else 1
    
    print(f"\nSearching Kayak for flights...")
    print("This may take 30-60 seconds...")
    print("-" * 40)
    
    # Perform Kayak search using Claude
    result = searcher.search_flights_with_claude(
        origin, destination, departure, return_date, passengers
    )
    
    print("\n" + "=" * 60)
    print("KAYAK FLIGHT SEARCH RESULTS")
    print("=" * 60)
    print(result)
    print("=" * 60)
    
    # Save results
    save_option = input("\nSave results to file? (y/n): ").strip().lower()
    if save_option == 'y':
        filename = f"kayak_flights_{origin}_{destination}_{departure.replace('-', '')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Kayak Flight Search Results\n")
            f.write(f"Route: {origin} to {destination}\n")
            f.write(f"Dates: {departure} - {return_date}\n")
            f.write(f"Passengers: {passengers}\n")
            f.write(f"Search Time: {datetime.now().isoformat()}\n\n")
            f.write(result)
        print(f"Results saved to {filename}")

if __name__ == "__main__":
    print("Kayak-Only Flight Search with Claude")
    print("Requires: anthropic library (pip install anthropic)")
    print()
    
    main()