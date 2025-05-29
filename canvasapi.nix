{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  requests,
  pytz,
  six,
  arrow,
}:
buildPythonPackage rec {
  pname = "canvasapi";
  version = "3.3.0"; # Replace with the version you need

  src = fetchFromGitHub {
    owner = "ucfopen";
    repo = pname;
    rev = "v${version}";
    hash = "sha256-2Ljx32hgLYcwBymbgK2QBZLSl8mFnluGjlqqRbiA5r0=";
  };

  propagatedBuildInputs = [
    requests
    pytz
    six
    arrow
  ];

  # Disable tests if they require network access or additional dependencies
  doCheck = false;

  meta = with lib; {
    description = "Python API wrapper for Canvas LMS";
    homepage = "https://github.com/ucfopen/canvasapi";
    license = licenses.mit;
    maintainers = with maintainers; [cgumb]; # Add your name if you plan to maintain it
  };
}
