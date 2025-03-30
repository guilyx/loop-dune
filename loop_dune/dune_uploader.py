import os
import requests
import argparse
import pandas as pd
from typing import Optional
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)


class DuneUploader:
    def __init__(self, api_key: str, namespace: str = "my_user"):
        self.api_key = api_key
        self.namespace = namespace
        self.base_url = "https://api.dune.com/api/v1"
        self.headers = {
            "X-DUNE-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        self.MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB in bytes

    def validate_column_names(self, df: pd.DataFrame) -> bool:
        """Validate that column names don't start with special characters or digits."""
        for col in df.columns:
            if not col[0].isalpha() and col[0] != "_":
                print(
                    f"{Fore.RED}Error: Column name '{col}' starts with a special character or digit{Style.RESET_ALL}"
                )
                return False
        return True

    def upload_csv(
        self, csv_path: str, table_name: str, description: Optional[str] = None
    ) -> bool:
        """
        Upload a CSV file directly to Dune as a new table.

        Args:
            csv_path: Path to the CSV file
            table_name: Name for the table in Dune
            description: Optional description of the table

        Returns:
            bool: True if upload was successful, False otherwise
        """
        if not os.path.exists(csv_path):
            print(f"{Fore.RED}Error: CSV file not found at {csv_path}{Style.RESET_ALL}")
            return False

        # Check file size
        file_size = os.path.getsize(csv_path)
        if file_size > self.MAX_FILE_SIZE:
            print(
                f"{Fore.RED}Error: File size ({file_size/1024/1024:.2f}MB) exceeds maximum allowed size (200MB){Style.RESET_ALL}"
            )
            return False

        try:
            # Read the CSV file with pandas to validate column names
            df = pd.read_csv(csv_path)
            if not self.validate_column_names(df):
                return False

            # Convert DataFrame back to CSV string
            csv_data = df.to_csv(index=False)

            # Prepare the request data
            data = {
                "data": csv_data,
                "table_name": table_name,  # Use the exact table name passed
                "description": description,  # Use the exact description passed
                "is_private": False,
            }

            # Make the request
            response = requests.post(
                f"{self.base_url}/table/upload/csv",
                headers=self.headers,
                json=data,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success", False):
                    print(
                        f"{Fore.GREEN}Successfully uploaded {csv_path} to Dune table: {result['table_name']}{Style.RESET_ALL}"
                    )
                    return True
                else:
                    print(
                        f"{Fore.RED}Error uploading {csv_path}: {response.text}{Style.RESET_ALL}"
                    )
                    return False
            else:
                print(
                    f"{Fore.RED}Error uploading {csv_path}: {response.text}{Style.RESET_ALL}"
                )
                return False

        except Exception as e:
            print(f"{Fore.RED}Error uploading {csv_path}: {str(e)}{Style.RESET_ALL}")
            return False

    def upload_all_csvs(self, data_dir: str) -> None:
        """
        Upload all CSV files in the data directory to Dune.

        Args:
            data_dir: Directory containing CSV files
        """
        if not os.path.exists(data_dir):
            print(
                f"{Fore.RED}Error: Data directory not found at {data_dir}{Style.RESET_ALL}"
            )
            return

        csv_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]

        if not csv_files:
            print(f"{Fore.YELLOW}No CSV files found in {data_dir}{Style.RESET_ALL}")
            return

        print(f"{Fore.CYAN}Found {len(csv_files)} CSV files to upload{Style.RESET_ALL}")

        for csv_file in csv_files:
            csv_path = os.path.join(data_dir, csv_file)
            table_name = csv_file.replace(
                ".csv", ""
            )  # Use filename without extension as table name

            print(f"\n{Fore.CYAN}Processing {csv_file}...{Style.RESET_ALL}")
            self.upload_csv(csv_path, table_name)


def main():
    parser = argparse.ArgumentParser(description="Upload CSV files to Dune")
    parser.add_argument(
        "--file",
        "-f",
        help="Path to the CSV file to upload",
        required=False,
    )
    parser.add_argument(
        "--namespace",
        "-n",
        help="Dune namespace (default: my_user)",
        default="my_user",
    )
    parser.add_argument(
        "--description",
        "-d",
        help="Description for the table",
        required=False,
    )
    parser.add_argument(
        "--all",
        "-a",
        help="Upload all CSV files from the data directory",
        action="store_true",
    )
    parser.add_argument(
        "--data-dir",
        help="Directory containing CSV files (default: data)",
        default="data",
    )

    args = parser.parse_args()

    # Get API key from environment variable
    api_key = os.getenv("DUNE_API_KEY")
    if not api_key:
        print(
            f"{Fore.RED}Error: DUNE_API_KEY environment variable not set{Style.RESET_ALL}"
        )
        return

    # Initialize uploader
    uploader = DuneUploader(api_key, namespace=args.namespace)

    if args.all:
        # Upload all CSV files
        uploader.upload_all_csvs(args.data_dir)
    elif args.file:
        # Upload single file with exact arguments
        uploader.upload_csv(args.file, args.namespace, args.description)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
