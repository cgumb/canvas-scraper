{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};

      # Define additional packages
      canvasapi = pkgs.python3Packages.callPackage ./canvasapi.nix {};
    in {
      devShells.default = pkgs.mkShell {
        name = "canvas-scraper";
        buildInputs = with pkgs.python3Packages; [
          canvasapi
          pathvalidate
          html2text
          python-dotenv
        ];
      };
    });
}
